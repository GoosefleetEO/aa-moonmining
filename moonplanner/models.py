import yaml

from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from esi.models import Token
from eveuniverse.models import EveMoon, EveSolarSystem, EveType

from allianceauth.authentication.models import CharacterOwnership
from allianceauth.eveonline.models import EveCorporationInfo
from allianceauth.services.hooks import get_extension_logger
from app_utils.datetime import ldap_time_2_datetime
from app_utils.logging import LoggerAddTag

from . import __title__, constants
from .app_settings import MOONPLANNER_REPROCESSING_YIELD, MOONPLANNER_VOLUME_PER_MONTH
from .providers import esi

logger = LoggerAddTag(get_extension_logger(__name__), __title__)
# MAX_DISTANCE_TO_MOON_METERS = 3000000


def calc_refined_value(
    eve_type: EveType, volume: float, reprocessing_yield: float
) -> float:
    """Calculate the refined total value of given eve_type and return it."""
    volume_per_unit = eve_type.volume
    units = volume / volume_per_unit
    r_units = units / 100
    value = 0
    for type_material in eve_type.materials.select_related(
        "material_eve_type__market_price"
    ):
        try:
            price = type_material.material_eve_type.market_price.average_price
        except (ObjectDoesNotExist, AttributeError):
            continue
        if price:
            value += price * type_material.quantity * r_units * reprocessing_yield
    return value


class MoonPlanner(models.Model):
    """Meta model for global app permissions"""

    class Meta:
        managed = False
        default_permissions = ()
        permissions = (
            ("access_moonplanner", "Can access the moonplanner app"),
            ("access_our_moons", "Can access our moons and see extractions"),
            ("access_all_moons", "Can access all moons in the database"),
            ("upload_moon_scan", "Can upload moon scans"),
            ("add_mining_corporation", "Can add mining corporation"),
        )


class Moon(models.Model):
    """Known moon through either survey data or anchored refinery.

    "Head" model for many of the other models
    """

    eve_moon = models.OneToOneField(
        EveMoon, on_delete=models.CASCADE, primary_key=True, related_name="income"
    )
    income = models.FloatField(
        null=True, default=None, validators=[MinValueValidator(0.0)]
    )
    products_updated_at = models.DateTimeField(null=True, default=None)
    products_updated_by = models.ForeignKey(
        User, on_delete=models.SET_DEFAULT, null=True, default=None
    )

    def __str__(self):
        return self.eve_moon.name

    def update_income_estimate(self, total_volume=None, reprocessing_yield=None):
        """Update income for this moon."""
        income = self.calc_income_estimate(
            total_volume=total_volume, reprocessing_yield=reprocessing_yield
        )
        self.income = income
        self.save()

    def calc_income_estimate(self, total_volume=None, reprocessing_yield=None) -> float:
        """Return calculated income estimate for given parameters.

        Args:
            total_volume: total excepted ore volume for this moon
            reprocessing_yield: expected average yield for ore reprocessing

        Returns:
            income estimate for moon or None if prices or products are missing
        """
        if not total_volume:
            total_volume = MOONPLANNER_VOLUME_PER_MONTH
        if not reprocessing_yield:
            reprocessing_yield = MOONPLANNER_REPROCESSING_YIELD
        income = 0
        for product in self.products.select_related("eve_type"):
            if product.eve_type.volume:
                income += calc_refined_value(
                    eve_type=product.eve_type,
                    volume=total_volume * product.amount,
                    reprocessing_yield=reprocessing_yield,
                )
        return income if income else None

    def is_owned(self):
        return hasattr(self, "refinery")


class MoonProduct(models.Model):
    """A product of a moon, i.e. a specifc ore."""

    moon = models.ForeignKey(Moon, on_delete=models.CASCADE, related_name="products")
    eve_type = models.ForeignKey(
        EveType,
        on_delete=models.DO_NOTHING,
        null=True,
        default=None,
        limit_choices_to=Q(group__category_id=25),
        related_name="+",
    )
    amount = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )

    def __str__(self):
        return "{} - {}".format(self.eve_type.name, self.amount)

    # class Meta:
    #     unique_together = (("eve_moon", "eve_type"),)
    #     indexes = [
    #         models.Index(fields=["eve_moon"]),
    #     ]

    def calc_income_estimate(self, total_volume=None, reprocessing_yield=None) -> float:
        """Return calculated income estimate for given parameters.

        Args:
            total_volume: total excepted ore volume for this moon
            reprocessing_yield: expected average yield for ore reprocessing

        Returns:
            income estimate for moon or None if prices or products are missing
        """
        if not total_volume:
            total_volume = MOONPLANNER_VOLUME_PER_MONTH
        if not reprocessing_yield:
            reprocessing_yield = MOONPLANNER_REPROCESSING_YIELD
        if not self.eve_type.volume:
            return None
        return calc_refined_value(
            eve_type=self.eve_type,
            volume=total_volume * self.amount,
            reprocessing_yield=reprocessing_yield,
        )


class MiningCorporation(models.Model):
    """An EVE Online corporation running mining operations."""

    corporation = models.OneToOneField(
        EveCorporationInfo,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="mining_corporations",
    )
    character_ownership = models.ForeignKey(
        CharacterOwnership,
        on_delete=models.SET_DEFAULT,
        default=None,
        null=True,
        help_text="character used to sync this corporation from ESI",
    )

    def __str__(self):
        return self.corporation.corporation_name

    def fetch_token(self):
        """Fetch token for this mining corp and return it..."""
        return (
            Token.objects.filter(
                character_id=self.character_ownership.character.character_id
            )
            .require_scopes(self.get_esi_scopes())
            .require_valid()
            .first()
        )

    def update_refineries_from_esi(self):
        """Update all refineries from ESI."""
        logger.info("%s: Fetching corp structures from ESI...", self)
        token = self.fetch_token()
        all_structures = (
            esi.client.Corporation.get_corporations_corporation_id_structures(
                corporation_id=self.corporation.corporation_id,
                token=token.valid_access_token(),
            ).result()
        )
        for refinery_info in all_structures:
            eve_type, _ = EveType.objects.get_or_create_esi(id=refinery_info["type_id"])
            if eve_type.eve_group_id == constants.EVE_GROUP_ID_REFINERY:
                structure_id = refinery_info["structure_id"]
                logger.info("%s: Fetching details for refinery #%d", self, structure_id)
                try:
                    structure_info = (
                        esi.client.Universe.get_universe_structures_structure_id(
                            structure_id=structure_id, token=token.valid_access_token()
                        ).result()
                    )
                except OSError:
                    logger.exception(
                        "%s: Failed to fetch refinery #%d", self, structure_id
                    )
                    continue
                refinery, _ = Refinery.objects.update_or_create(
                    id=structure_id,
                    defaults={
                        "name": structure_info["name"],
                        "eve_type": eve_type,
                        "corporation": self,
                    },
                )
                if not refinery.moon:
                    # determine moon next to refinery
                    solar_system, _ = EveSolarSystem.objects.get_or_create_esi(
                        id=structure_info["solar_system_id"]
                    )
                    try:
                        nearest_celestial = solar_system.nearest_celestial(
                            structure_info["position"]["x"],
                            structure_info["position"]["y"],
                            structure_info["position"]["z"],
                        )
                    except OSError:
                        logger.exception(
                            "%s: Failed to fetch nearest celestial for refinery #%d",
                            self,
                            structure_id,
                        )
                    else:
                        if (
                            nearest_celestial
                            and nearest_celestial.eve_type.id
                            == constants.EVE_TYPE_ID_MOON
                        ):
                            eve_moon = nearest_celestial.eve_object
                            moon, _ = Moon.objects.get_or_create(eve_moon=eve_moon)
                            refinery.moon = moon
                            refinery.save()

    def update_extractions_from_esi(self):
        """Update all extractions from ESI."""
        logger.info("%s: Updating extractions from ESI...", self)
        token = self.fetch_token()
        all_notifications = (
            esi.client.Character.get_characters_character_id_notifications(
                character_id=self.character_ownership.character.character_id,
                token=token.valid_access_token(),
            ).result()
        )
        notifications = [
            notif
            for notif in all_notifications
            if notif["type"]
            in {
                "MoonminingAutomaticFracture",
                "MoonminingExtractionCancelled",
                "MoonminingExtractionFinished",
                "MoonminingExtractionStarted",
                "MoonminingLaserFired",
            }
        ]
        if not notifications:
            logger.info("%s: No moon notifications received", self)
            return

        # add extractions for refineries if any are found
        logger.info(
            "%s: Process extraction events from %d moon notifications",
            self,
            len(notifications),
        )
        last_extraction_started = dict()
        moon_updated = False
        for notification in sorted(notifications, key=lambda k: k["timestamp"]):
            parsed_text = yaml.safe_load(notification["text"])
            structure_id = parsed_text["structureID"]
            try:
                refinery = Refinery.objects.get(id=structure_id)
            except Refinery.DoesNotExist:
                refinery = None
            # update the refinery's moon in case it was not found by nearest_celestial
            if refinery and not moon_updated:
                moon_updated = True
                eve_moon, _ = EveMoon.objects.get_or_create_esi(
                    id=parsed_text["moonID"]
                )
                moon, _ = Moon.objects.get_or_create(eve_moon=eve_moon)
                if refinery.moon != moon:
                    refinery.moon = moon
                    refinery.save()

            if notification["type"] == "MoonminingExtractionStarted":
                if not refinery:
                    continue  # we ignore notifications for unknown refineries
                extraction, _ = Extraction.objects.get_or_create(
                    refinery=refinery,
                    ready_time=ldap_time_2_datetime(parsed_text["readyTime"]),
                    defaults={
                        "auto_time": ldap_time_2_datetime(parsed_text["autoTime"])
                    },
                )
                last_extraction_started[id] = extraction
                ore_volume_by_type = parsed_text["oreVolumeByType"].items()
                for ore_type_id, ore_volume in ore_volume_by_type:
                    eve_type, _ = EveType.objects.get_or_create_esi(
                        id=ore_type_id,
                        enabled_sections=[EveType.Section.TYPE_MATERIALS],
                    )
                    ExtractionProduct.objects.get_or_create(
                        extraction=extraction,
                        eve_type=eve_type,
                        defaults={"volume": ore_volume},
                    )

            # remove latest started extraction if it was canceled
            # and not finished
            if notification["type"] == "MoonminingExtractionCancelled":
                if structure_id in last_extraction_started:
                    extraction = last_extraction_started[structure_id]
                    extraction.delete()

            if notification["type"] == "MoonminingExtractionFinished":
                if structure_id in last_extraction_started:
                    del last_extraction_started[structure_id]

            # TODO: test logic to handle canceled extractions

    @classmethod
    def get_esi_scopes(cls):
        return [
            "esi-industry.read_corporation_mining.v1",
            "esi-universe.read_structures.v1",
            "esi-characters.read_notifications.v1",
            "esi-corporations.read_structures.v1",
        ]


class Refinery(models.Model):
    """An Eve Online refinery structure."""

    id = models.BigIntegerField(primary_key=True)
    name = models.CharField(max_length=150)
    moon = models.OneToOneField(
        Moon,
        on_delete=models.SET_DEFAULT,
        default=None,
        null=True,
        related_name="refinery",
    )
    corporation = models.ForeignKey(MiningCorporation, on_delete=models.CASCADE)
    eve_type = models.ForeignKey(
        EveType,
        on_delete=models.CASCADE,
        limit_choices_to={"eve_group_id": constants.EVE_GROUP_ID_REFINERY},
        related_name="+",
    )

    def __str__(self):
        return self.name


class Extraction(models.Model):
    """A mining extraction."""

    refinery = models.ForeignKey(
        Refinery, on_delete=models.CASCADE, related_name="extractions"
    )
    ready_time = models.DateTimeField()
    auto_time = models.DateTimeField()

    # class Meta:
    #     unique_together = (("ready_time", "refinery"),)

    def __str__(self):
        return "{} - {}".format(self.refinery, self.ready_time)


class ExtractionProduct(models.Model):
    """A product within a mining extraction."""

    extraction = models.ForeignKey(
        Extraction, on_delete=models.CASCADE, related_name="products"
    )
    eve_type = models.ForeignKey(
        EveType,
        on_delete=models.CASCADE,
        limit_choices_to=Q(
            eve_group__eve_category_id=constants.EVE_CATEGORY_ID_ASTEROID
        ),
    )
    volume = models.FloatField(validators=[MinValueValidator(0.0)])

    # class Meta:
    #     unique_together = (("extraction", "eve_type"),)

    def __str__(self):
        return "{} - {}".format(self.extraction, self.eve_type)

    def calc_value_estimate(self, reprocessing_yield=None) -> float:
        """returns calculated value estimate in ISK

        Args:
            reprocessing_yield: expected average yield for ore reprocessing
        Returns:
            value estimate or None if prices are missing

        """
        if not reprocessing_yield:
            reprocessing_yield = MOONPLANNER_REPROCESSING_YIELD

        return calc_refined_value(
            eve_type=self.eve_type,
            volume=self.volume,
            reprocessing_yield=reprocessing_yield,
        )
