from collections import namedtuple
from concurrent import futures
from typing import Tuple

from django.contrib.auth.models import User
from django.db import models, transaction
from django.db.models import ExpressionWrapper, F, FloatField, Sum
from django.db.models.functions import Coalesce
from django.utils.timezone import now
from eveuniverse.managers import EveTypeManager
from eveuniverse.models import EveMoon

from allianceauth.notifications import notify
from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag

from . import __title__, constants
from .core import CalculatedExtraction
from .helpers import eveentity_get_or_create_esi_safe

MAX_THREAD_WORKERS = 20
BULK_BATCH_SIZE = 500
logger = LoggerAddTag(get_extension_logger(__name__), __title__)

SurveyProcessResult = namedtuple(
    "SurveyProcessResult", ["moon_name", "success", "error_name"]
)


class EveOreTypeManger(EveTypeManager):
    def get_queryset(self):
        """Return ore types only."""
        return (
            super()
            .get_queryset()
            .select_related("eve_group")
            .filter(published=True)
            .filter(eve_group__eve_category_id=constants.EVE_CATEGORY_ID_ASTEROID)
        )

    def update_refined_prices(self):
        """Update refined prices for all EveOreTypes"""
        from .models import EveOreTypeExtras

        for obj in self.all():
            EveOreTypeExtras.objects.update_or_create(
                ore_type=obj,
                defaults={"refined_price": obj.calc_refined_value_per_unit},
            )


class MiningLedgerRecordManager(models.Manager):
    def get_queryset(self):
        """Add calculated values to all object."""
        sum_price = ExpressionWrapper(
            F("quantity") * Coalesce(F("unit_price"), 0),
            output_field=FloatField(),
        )
        return (
            super()
            .get_queryset()
            .select_related("ore_type", "ore_type__extras")
            .annotate(unit_price=F("ore_type__extras__refined_price"))
            .annotate(total_price=Sum(sum_price, distinct=True))
        )


class UpdateCalculatedPropertiesMixin:
    """Mixin for updating all calculated properties of a query set"""

    def update_calculated_properties(self):
        logger.info(
            "Updating calculated properties for %d %ss ...",
            len(self),
            self.model.__name__.lower(),
        )
        with futures.ThreadPoolExecutor(max_workers=MAX_THREAD_WORKERS) as executor:
            executor.map(self._thread_update_obj, list(self))
        logger.info("Completed calculating properties.")

    def _thread_update_obj(self, obj):
        logger.info(
            "Updating calculated properties for %s %d...", self.model.__name__, obj.pk
        )
        obj.update_calculated_properties()


class MoonQuerySet(models.QuerySet, UpdateCalculatedPropertiesMixin):
    pass


class MoonManager(models.Manager):
    def get_queryset(self) -> models.QuerySet:
        return MoonQuerySet(self.model, using=self._db)

    def selected_related_defaults(self) -> models.QuerySet:
        return self.select_related(
            "eve_moon",
            "eve_moon__eve_planet__eve_solar_system",
            "eve_moon__eve_planet__eve_solar_system__eve_constellation__eve_region",
            "refinery",
            "refinery__eve_type",
            "refinery__owner",
            "refinery__owner__corporation",
            "refinery__owner__corporation__alliance",
        )

    def update_moons_from_survey(self, scans: str, user: User = None) -> bool:
        """Update moons from survey input.

        Args:
            scans: raw text input from user containing moon survey data
            user: (optional) user who submitted the data
        """
        surveys, error_name = self._parse_scans(scans)
        if surveys:
            process_results, success = self._process_surveys(surveys, user)
        else:
            process_results = None
            success = False

        if user:
            success = self._send_survey_process_report_to_user(
                process_results, error_name, user, success
            )
        return success

    @staticmethod
    def _parse_scans(scans: str) -> tuple:
        surveys = []
        try:
            lines = scans.split("\n")
            lines_ = []
            for line in lines:
                line = line.strip("\r").split("\t")
                lines_.append(line)
            lines = lines_

            # Find all groups of scans.
            if len(lines[0]) == 0 or lines[0][0] == "Moon":
                lines = lines[1:]
            sublists = []
            for line in lines:
                # Find the lines that start a scan
                if line[0] == "":
                    pass
                else:
                    sublists.append(lines.index(line))

            # Separate out individual surveys
            for i in range(len(sublists)):
                # The First List
                if i == 0:
                    if i + 2 > len(sublists):
                        surveys.append(lines[sublists[i] :])
                    else:
                        surveys.append(lines[sublists[i] : sublists[i + 1]])
                else:
                    if i + 2 > len(sublists):
                        surveys.append(lines[sublists[i] :])
                    else:
                        surveys.append(lines[sublists[i] : sublists[i + 1]])

        except Exception as ex:
            logger.warning(
                "An issue occurred while trying to parse the surveys", exc_info=True
            )
            error_name = type(ex).__name__

        else:
            error_name = ""
        return surveys, error_name

    def _process_surveys(self, surveys: list, user: User) -> Tuple[list, bool]:
        from .models import EveOreType, MoonProduct

        overall_success = True
        process_results = list()
        for survey in surveys:
            moon_name = ""
            try:
                moon_name = survey[0][0]
                moon_id = survey[1][6]
                eve_moon, _ = EveMoon.objects.get_or_create_esi(id=moon_id)
                moon, _ = self.get_or_create(eve_moon=eve_moon)
                moon.products_updated_by = user
                moon.products_updated_at = now()
                moon_products = list()
                survey = survey[1:]
                for product_data in survey:
                    # Trim off the empty index at the front
                    product_data = product_data[1:]
                    ore_type, _ = EveOreType.objects.get_or_create_esi(
                        id=product_data[2]
                    )
                    moon_products.append(
                        MoonProduct(
                            moon=moon, amount=product_data[1], ore_type=ore_type
                        )
                    )

                with transaction.atomic():
                    moon.products.all().delete()
                    MoonProduct.objects.bulk_create(moon_products, batch_size=500)

                moon.update_calculated_properties()
                logger.info("Added moon survey for %s", moon.name)

            except Exception as ex:
                logger.warning(
                    "An issue occurred while processing the following moon survey: %s",
                    survey,
                    exc_info=True,
                )
                error_name = type(ex).__name__
                overall_success = success = False
            else:
                success = True
                error_name = None

            process_results.append(
                SurveyProcessResult(
                    moon_name=moon_name, success=success, error_name=error_name
                )
            )
        return process_results, overall_success

    @staticmethod
    def _send_survey_process_report_to_user(
        process_results: list, error_name: str, user: User, success: bool
    ) -> bool:
        message = "We have completed processing your moon survey input:\n\n"
        if process_results:
            for num, process_result in enumerate(process_results):
                moon_name = process_result.moon_name
                if process_result.success:
                    status = "OK"
                    error_name = ""
                else:
                    status = "FAILED"
                    success = False
                    error_name = "- {}".format(process_result.error_name)
                message += "#{}: {}: {} {}\n".format(
                    num + 1, moon_name, status, error_name
                )
        else:
            message += "\nProcessing failed"

        notify(
            user=user,
            title="Moon survey input processing results: {}".format(
                "OK" if success else "FAILED"
            ),
            message=message,
            level="success" if success else "danger",
        )
        return success


class ExtractionQuerySet(models.QuerySet, UpdateCalculatedPropertiesMixin):
    def selected_related_defaults(self) -> models.QuerySet:
        return self.select_related(
            "refinery",
            "refinery__moon",
            "refinery__moon__eve_moon",
            "refinery__owner",
            "refinery__owner__corporation",
            "refinery__owner__corporation__alliance",
        )

    def update_status(self):
        """Update status of given extractions according to current time."""
        self.exclude(
            status__in=[self.model.Status.READY, self.model.Status.CANCELED]
        ).filter(chunk_arrival_at__lte=now(), auto_fracture_at__gt=now(),).update(
            status=self.model.Status.READY
        )
        self.exclude(
            status__in=[self.model.Status.COMPLETED, self.model.Status.CANCELED]
        ).filter(auto_fracture_at__lte=now()).update(status=self.model.Status.COMPLETED)


class ExtractionManager(models.Manager):
    def annotate_volume(self) -> models.QuerySet:
        """Add volume of all products"""
        return self.annotate(volume=Sum("products__volume"))

    def get_queryset(self) -> models.QuerySet:
        return ExtractionQuerySet(self.model, using=self._db)

    def update_from_calculated(self, calculated: CalculatedExtraction) -> bool:
        """Update an extraction object from related calculated extraction
        when there is new information.

        Return True when updated, else False.
        """
        from .models import EveOreType, ExtractionProduct

        if calculated.chunk_arrival_at:
            try:
                extraction = self.get(
                    refinery_id=calculated.refinery_id,
                    chunk_arrival_at=calculated.chunk_arrival_at,
                )
            except self.model.DoesNotExist:
                logger.debug("%s: Could not find matching extraction", calculated)
                return False
        elif calculated.auto_fracture_at:
            try:
                extraction = self.get(
                    refinery_id=calculated.refinery_id,
                    auto_fracture_at=calculated.auto_fracture_at,
                )
            except self.model.DoesNotExist:
                logger.debug("%s: Could not find matching extraction", calculated)
                return False
        else:
            logger.debug(
                "%s: Not enough data to search for matching extraction", calculated
            )
            return False

        needs_update = False
        if calculated.canceled_at and not extraction.canceled_at:
            extraction.canceled_at = calculated.canceled_at
            needs_update = True
        if calculated.canceled_by and not extraction.canceled_by:
            extraction.canceled_by = eveentity_get_or_create_esi_safe(
                calculated.canceled_by
            )
            needs_update = True
        if calculated.canceled_by and not extraction.canceled_by:
            extraction.canceled_by = eveentity_get_or_create_esi_safe(
                calculated.canceled_by
            )
            needs_update = True
        if calculated.fractured_by and not extraction.fractured_by:
            extraction.fractured_by = eveentity_get_or_create_esi_safe(
                calculated.fractured_by
            )
            needs_update = True
        if calculated.fractured_at and not extraction.fractured_at:
            extraction.fractured_at = calculated.fractured_at
            needs_update = True
        if self.model.Status.from_calculated(calculated) != extraction.status:
            extraction.status = self.model.Status.from_calculated(calculated)
            needs_update = True
            status_changed = True
        else:
            status_changed = False
        if calculated.started_by and not extraction.started_by:
            extraction.started_by = eveentity_get_or_create_esi_safe(
                calculated.started_by
            )
            needs_update = True
        updated = False
        if needs_update:
            extraction.save()
            updated = True
        if calculated.products and (status_changed or not extraction.products.exists()):
            # preload eve ore types before transaction starts
            EveOreType.objects.bulk_get_or_create_esi(
                ids=[product.ore_type_id for product in calculated.products]
            )
            products = [
                ExtractionProduct(
                    extraction=extraction,
                    ore_type_id=product.ore_type_id,
                    volume=product.volume,
                )
                for product in calculated.products
            ]
            with transaction.atomic():
                ExtractionProduct.objects.filter(extraction=extraction).delete()
                ExtractionProduct.objects.bulk_create(
                    products, batch_size=BULK_BATCH_SIZE
                )
            extraction.update_calculated_properties()
            updated = True
        return updated
