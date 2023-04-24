import datetime as dt
from collections import defaultdict
from enum import Enum
from typing import Iterable, List, Optional

import yaml

from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import F, Sum, Value
from django.db.models.functions import Coalesce
from django.utils.functional import cached_property, classproperty
from django.utils.html import format_html
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from esi.models import Token
from eveuniverse.models import EveEntity, EveMoon, EveSolarSystem, EveType

from allianceauth.authentication.models import CharacterOwnership
from allianceauth.eveonline.models import EveCorporationInfo
from allianceauth.services.hooks import get_extension_logger
from app_utils.allianceauth import notify_admins_throttled
from app_utils.datetime import ldap_time_2_datetime
from app_utils.logging import LoggerAddTag
from app_utils.views import (
    BootstrapStyle,
    bootstrap_icon_plus_name_html,
    bootstrap_label_html,
)

from . import __title__
from .app_settings import (
    MOONMINING_OVERWRITE_SURVEYS_WITH_ESTIMATES,
    MOONMINING_REPROCESSING_YIELD,
    MOONMINING_VOLUME_PER_DAY,
    MOONMINING_VOLUME_PER_MONTH,
)
from .constants import EveDogmaAttributeId, EveGroupId, EveTypeId, IconSize
from .core import CalculatedExtraction, CalculatedExtractionProduct
from .managers import (
    EveOreTypeManger,
    ExtractionManager,
    MiningLedgerRecordManager,
    MoonManager,
    RefineryManager,
)
from .providers import esi

logger = LoggerAddTag(get_extension_logger(__name__), __title__)
# MAX_DISTANCE_TO_MOON_METERS = 3000000


class NotificationType(str, Enum):
    """ESI notification types used in this app."""

    MOONMINING_AUTOMATIC_FRACTURE = "MoonminingAutomaticFracture"
    MOONMINING_EXTRACTION_CANCELLED = "MoonminingExtractionCancelled"
    MOONMINING_EXTRACTION_FINISHED = "MoonminingExtractionFinished"
    MOONMINING_EXTRACTION_STARTED = "MoonminingExtractionStarted"
    MOONMINING_LASER_FIRED = "MoonminingLaserFired"

    def __str__(self) -> str:
        return self.value

    @classproperty
    def all_moon_mining(cls) -> set:
        """Return all moon mining notifications"""
        return {
            cls.MOONMINING_AUTOMATIC_FRACTURE,
            cls.MOONMINING_EXTRACTION_CANCELLED,
            cls.MOONMINING_EXTRACTION_FINISHED,
            cls.MOONMINING_EXTRACTION_STARTED,
            cls.MOONMINING_LASER_FIRED,
        }

    @classproperty
    def with_products(cls) -> set:
        """Return all notification types with have products."""
        return {
            cls.MOONMINING_AUTOMATIC_FRACTURE,
            cls.MOONMINING_EXTRACTION_FINISHED,
            cls.MOONMINING_EXTRACTION_STARTED,
            cls.MOONMINING_LASER_FIRED,
        }


class OreRarityClass(models.IntegerChoices):
    """Rarity class of an ore"""

    NONE = 0, ""
    R4 = 4, _("R 4")
    R8 = 8, _("R 8")
    R16 = 16, _("R16")
    R32 = 32, _("R32")
    R64 = 64, _("R64")

    @property
    def bootstrap_tag_html(self) -> str:
        map_rarity_to_type = {
            self.R4: BootstrapStyle.PRIMARY,
            self.R8: BootstrapStyle.INFO,
            self.R16: BootstrapStyle.SUCCESS,
            self.R32: BootstrapStyle.WARNING,
            self.R64: BootstrapStyle.DANGER,
        }
        try:
            return bootstrap_label_html(
                f"R{self.value}", label=map_rarity_to_type[self].value
            )
        except KeyError:
            return ""

    @classmethod
    def from_eve_group_id(cls, eve_group_id: int) -> "OreRarityClass":
        """Create object from eve group ID"""
        map_group_2_rarity = {
            EveGroupId.UBIQUITOUS_MOON_ASTEROIDS.value: cls.R4,
            EveGroupId.COMMON_MOON_ASTEROIDS.value: cls.R8,
            EveGroupId.UNCOMMON_MOON_ASTEROIDS.value: cls.R16,
            EveGroupId.RARE_MOON_ASTEROIDS.value: cls.R32,
            EveGroupId.EXCEPTIONAL_MOON_ASTEROIDS.value: cls.R64,
        }
        try:
            return map_group_2_rarity[eve_group_id]
        except KeyError:
            return cls.NONE

    @classmethod
    def from_eve_type(cls, eve_type: EveType) -> "OreRarityClass":
        """Create object from eve type"""
        return cls.from_eve_group_id(eve_type.eve_group_id)


class OreQualityClass(models.TextChoices):
    """Quality class of an ore"""

    UNDEFINED = "UN", _("undefined")
    REGULAR = "RE", _("regular")
    IMPROVED = "IM", _("improved")
    EXCELLENT = "EX", _("excellent")

    @property
    def bootstrap_tag_html(self) -> str:
        """Return bootstrap tag."""
        map_quality_to_label_def = {
            self.IMPROVED: {"text": "+15%", "label": BootstrapStyle.SUCCESS},
            self.EXCELLENT: {"text": "+100%", "label": BootstrapStyle.WARNING},
        }
        try:
            label_def = map_quality_to_label_def[self]
            return bootstrap_label_html(label_def["text"], label=label_def["label"])
        except KeyError:
            return ""

    @classmethod
    def from_eve_type(cls, eve_type: EveType) -> "OreQualityClass":
        """Create object from given eve type."""
        map_value_2_quality_class = {
            1: cls.REGULAR,
            3: cls.IMPROVED,
            5: cls.EXCELLENT,
        }
        try:
            dogma_attribute = eve_type.dogma_attributes.get(
                eve_dogma_attribute_id=EveDogmaAttributeId.ORE_QUALITY
            )
        except ObjectDoesNotExist:
            return cls.UNDEFINED
        try:
            return map_value_2_quality_class[int(dogma_attribute.value)]
        except KeyError:
            return cls.UNDEFINED


class EveOreType(EveType):
    """Subset of EveType for all ore types.

    Ensures TYPE_MATERIALS and DOGMAS is always enabled and allows adding methods to types.
    """

    class Meta:
        proxy = True
        verbose_name = _("ore type")
        verbose_name_plural = _("ore types")

    objects = EveOreTypeManger()

    @property
    def icon_url_32(self) -> str:
        return self.icon_url(32)

    @property
    def rarity_class(self) -> OreRarityClass:
        return OreRarityClass.from_eve_type(self)

    @cached_property
    def quality_class(self) -> OreQualityClass:
        return OreQualityClass.from_eve_type(self)

    @cached_property
    def price(self) -> float:
        """Return calculated price estimate in ISK per unit."""
        result = self.extras.current_price
        return result if result is not None else 0.0

    def price_by_volume(self, volume: int) -> Optional[float]:
        """Return calculated price estimate in ISK for volume in m3."""
        return self.price_by_units(int(volume // self.volume)) if self.volume else None

    def price_by_units(self, units: int) -> float:
        """Return calculated price estimate in ISK for units."""
        return self.price * units

    def calc_refined_value_per_unit(
        self, reprocessing_yield: Optional[float] = None
    ) -> float:
        """Calculate the refined total value per unit and return it."""
        if not reprocessing_yield:
            reprocessing_yield = MOONMINING_REPROCESSING_YIELD
        units = 10000
        r_units = units / 100
        value = 0
        for type_material in self.materials.select_related(
            "material_eve_type__market_price"
        ):
            try:
                price = type_material.material_eve_type.market_price.average_price
            except (ObjectDoesNotExist, AttributeError):
                continue
            if price:
                value += price * type_material.quantity * r_units * reprocessing_yield
        return value / units

    @classmethod
    def _enabled_sections_union(cls, enabled_sections: Iterable[str]) -> set:
        """Return enabled sections with TYPE_MATERIALS and DOGMAS always enabled."""
        enabled_sections = super()._enabled_sections_union(
            enabled_sections=enabled_sections
        )
        enabled_sections.add(cls.Section.TYPE_MATERIALS)
        enabled_sections.add(cls.Section.DOGMAS)
        return enabled_sections


class EveOreTypeExtras(models.Model):
    """Extra fields for an EveOreType, e.g. for pricing calculations."""

    class PricingMethod(models.TextChoices):
        UNKNOWN = "UN", _("Undefined")
        EVE_CLIENT = "EC", _("Eve client")
        REPROCESSED_MATERIALS = "RP", _("Reprocessed materials")

    ore_type = models.OneToOneField(
        EveOreType, on_delete=models.CASCADE, related_name="extras"
    )
    current_price = models.FloatField(
        default=None,
        null=True,
        help_text=_("Price used by all price calculations with this type"),
    )
    pricing_method = models.CharField(
        max_length=2, choices=PricingMethod.choices, default=PricingMethod.UNKNOWN
    )

    class Meta:
        verbose_name = _("ore type extra")
        verbose_name_plural = _("ore type extras")

    def __str__(self) -> str:
        return str(self.ore_type)


class Extraction(models.Model):
    """A mining extraction."""

    class Status(models.TextChoices):
        STARTED = "ST", _("started")  # has been started
        CANCELED = "CN", _("canceled")  # has been canceled
        READY = "RD", _("ready")  # has finished extraction and is ready to be fractured
        COMPLETED = "CP", _("completed")  # has been fractured
        UNDEFINED = "UN", _("undefined")  # unclear status

        @property
        def bootstrap_tag_html(self) -> str:
            map_to_type = {
                self.STARTED: BootstrapStyle.SUCCESS,
                self.CANCELED: BootstrapStyle.DANGER,
                self.READY: BootstrapStyle.WARNING,
                self.COMPLETED: BootstrapStyle.PRIMARY,
                self.UNDEFINED: "",
            }
            try:
                return bootstrap_label_html(self.label, label=map_to_type[self].value)
            except KeyError:
                return ""

        @property
        def to_notification_type(self) -> NotificationType:
            map_to_type = {
                self.STARTED: NotificationType.MOONMINING_EXTRACTION_STARTED,
                self.CANCELED: NotificationType.MOONMINING_EXTRACTION_CANCELLED,
                self.READY: NotificationType.MOONMINING_EXTRACTION_FINISHED,
                self.COMPLETED: NotificationType.MOONMINING_LASER_FIRED,
            }
            try:
                return map_to_type[self]
            except KeyError:
                raise ValueError("Invalid status for notification type") from None

        @classproperty
        def considered_active(cls):
            return [cls.STARTED, cls.READY]

        @classproperty
        def considered_inactive(cls):
            return [cls.CANCELED, cls.COMPLETED]

        @classmethod
        def from_calculated(cls, calculated):
            map_from_calculated = {
                CalculatedExtraction.Status.STARTED: cls.STARTED,
                CalculatedExtraction.Status.CANCELED: cls.CANCELED,
                CalculatedExtraction.Status.READY: cls.READY,
                CalculatedExtraction.Status.COMPLETED: cls.COMPLETED,
                CalculatedExtraction.Status.UNDEFINED: cls.UNDEFINED,
            }
            try:
                return map_from_calculated[calculated.status]
            except KeyError:
                return cls.UNDEFINED

    # PK
    refinery = models.ForeignKey(
        "Refinery", on_delete=models.CASCADE, related_name="extractions"
    )
    started_at = models.DateTimeField(
        db_index=True, help_text=_("When this extraction was started")
    )
    # normal properties
    auto_fracture_at = models.DateTimeField(
        help_text=_("When this extraction will be automatically fractured"),
    )
    canceled_at = models.DateTimeField(
        null=True, default=None, help_text=_("When this extraction was canceled")
    )
    canceled_by = models.ForeignKey(
        EveEntity,
        on_delete=models.SET_DEFAULT,
        null=True,
        default=None,
        related_name="+",
        help_text=_("Eve character who canceled this extraction"),
    )
    chunk_arrival_at = models.DateTimeField(
        db_index=True, help_text=_("When this extraction is ready to be fractured")
    )
    fractured_at = models.DateTimeField(
        null=True, default=None, help_text=_("When this extraction was fractured")
    )
    fractured_by = models.ForeignKey(
        EveEntity,
        on_delete=models.SET_DEFAULT,
        null=True,
        default=None,
        related_name="+",
        help_text=_("Eve character who fractured this extraction (if any)"),
    )
    is_jackpot = models.BooleanField(
        default=None,
        null=True,
        help_text=_("Whether this is a jackpot extraction (calculated)"),
    )
    started_by = models.ForeignKey(
        EveEntity,
        on_delete=models.SET_DEFAULT,
        null=True,
        default=None,
        related_name="+",
        help_text=_("Eve character who started this extraction"),
    )
    status = models.CharField(
        max_length=2, choices=Status.choices, default=Status.UNDEFINED, db_index=True
    )
    value = models.FloatField(
        null=True,
        default=None,
        validators=[MinValueValidator(0.0)],
        help_text=_("Estimated value of this extraction (calculated)"),
    )

    objects = ExtractionManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["refinery", "started_at"], name="functional_pk_extraction"
            )
        ]
        verbose_name = _("extraction")
        verbose_name_plural = _("extractions")

    def __str__(self) -> str:
        return f"{self.refinery} - {self.started_at} - {self.status}"

    @property
    def duration(self) -> dt.timedelta:
        """Duration of this extraction."""
        return self.chunk_arrival_at - self.started_at

    @property
    def duration_in_days(self) -> float:
        """Duration of this extraction in days."""
        return self.duration.total_seconds() / (60 * 60 * 24)

    @property
    def status_enum(self) -> "Extraction.Status":
        """Return current status as enum type."""
        return self.Status(self.status)

    def products_sorted(self):
        """Return current products as sorted iterable."""
        try:
            return (
                self.products.select_related(
                    "ore_type", "ore_type__eve_group", "ore_type__extras"
                )
                .annotate(total_price=self._total_price_db_func())
                .order_by("ore_type__name")
            )
        except (ObjectDoesNotExist, AttributeError):
            return type(self).objects.none()

    @cached_property
    def ledger(self) -> models.QuerySet:
        """Return ledger for this extraction."""
        max_day = self.chunk_arrival_at + dt.timedelta(days=6)
        return self.refinery.mining_ledger.filter(
            day__gte=self.chunk_arrival_at,
            day__lte=max_day,
        )

    def calc_value(self) -> Optional[float]:
        """Calculate value estimate."""
        try:
            return self.products.select_related(
                "ore_type", "ore_type__extras"
            ).aggregate(total_price=self._total_price_db_func())["total_price"]
        except (ObjectDoesNotExist, KeyError, AttributeError):
            return None

    @staticmethod
    def _total_price_db_func():
        return Sum(
            Coalesce(F("ore_type__extras__current_price"), 0.0)
            * F("volume")
            / F("ore_type__volume"),
            output_field=models.FloatField(),
        )

    def calc_is_jackpot(self) -> Optional[bool]:
        """Calculate if extraction is jackpot and return result.
        Return None if extraction has no products.
        """
        try:
            products_qualities = [
                product.ore_type.quality_class == OreQualityClass.EXCELLENT
                for product in self.products.select_related("ore_type").all()
            ]
        except (ObjectDoesNotExist, AttributeError):
            return None
        else:
            if not products_qualities:
                return None
            return all(products_qualities)

    def update_calculated_properties(self) -> None:
        """Update calculated properties for this extraction."""
        self.value = self.calc_value()
        self.is_jackpot = self.calc_is_jackpot()
        self.save()

    def to_calculated_extraction(self) -> CalculatedExtraction:
        """Generate a calculated extraction from this extraction."""

        def _products_to_calculated_products():
            return [
                CalculatedExtractionProduct(
                    ore_type_id=obj.ore_type_id, volume=obj.volume
                )
                for obj in self.products.all()
            ]

        params = {"refinery_id": self.refinery_id}
        if self.status == self.Status.STARTED:
            params.update(
                {
                    "status": CalculatedExtraction.Status.STARTED,
                    "chunk_arrival_at": self.chunk_arrival_at,
                    "auto_fracture_at": self.auto_fracture_at,
                    "started_at": self.started_at,
                    "started_by": self.started_by,
                    "products": _products_to_calculated_products(),
                }
            )
        elif self.status == self.Status.READY:
            params.update(
                {
                    "status": CalculatedExtraction.Status.READY,
                    "auto_fracture_at": self.auto_fracture_at,
                    "products": _products_to_calculated_products(),
                }
            )
        elif self.status == self.Status.COMPLETED:
            params.update(
                {
                    "fractured_by": self.fractured_by,
                    "fractured_at": self.fractured_at,
                    "status": CalculatedExtraction.Status.COMPLETED,
                    "products": _products_to_calculated_products(),
                }
            )
        elif self.status == self.Status.CANCELED:
            params.update(
                {
                    "status": CalculatedExtraction.Status.CANCELED,
                    "canceled_at": self.canceled_at,
                    "canceled_by": self.canceled_by,
                }
            )
        return CalculatedExtraction(**params)


class ExtractionProduct(models.Model):
    """A product within a mining extraction."""

    extraction = models.ForeignKey(
        Extraction, on_delete=models.CASCADE, related_name="products"
    )
    ore_type = models.ForeignKey(EveOreType, on_delete=models.CASCADE, related_name="+")

    volume = models.FloatField(validators=[MinValueValidator(0.0)])

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["extraction", "ore_type"],
                name="functional_pk_extractionproduct",
            )
        ]
        verbose_name = _("extraction product")
        verbose_name_plural = _("extractions products")

    def __str__(self) -> str:
        return f"{self.extraction} - {self.ore_type}"


class Label(models.Model):
    """A custom label for structuring moons."""

    class Style(models.TextChoices):
        DARK_BLUE = "primary", _("dark blue")
        GREEN = "success", _("green")
        GREY = "default", _("grey")
        LIGHT_BLUE = "info", _("light blue")
        ORANGE = "warning", _("orange")
        RED = "danger", _("red")

        @property
        def bootstrap_style(self) -> str:
            map_to_type = {
                self.DARK_BLUE: BootstrapStyle.PRIMARY,
                self.GREEN: BootstrapStyle.SUCCESS,
                self.LIGHT_BLUE: BootstrapStyle.INFO,
                self.ORANGE: BootstrapStyle.WARNING,
                self.RED: BootstrapStyle.DANGER,
            }
            try:
                return map_to_type[self].value
            except KeyError:
                return BootstrapStyle.DEFAULT

    description = models.TextField(default="", blank=True)
    name = models.CharField(max_length=100, unique=True)
    style = models.CharField(max_length=16, choices=Style.choices, default=Style.GREY)

    class Meta:
        verbose_name = _("label")
        verbose_name_plural = _("labels")

    def __str__(self) -> str:
        return self.name

    @property
    def tag_html(self) -> str:
        label_style = self.Style(self.style).bootstrap_style
        return bootstrap_label_html(self.name, label=label_style)


class General(models.Model):
    """Meta model for global app permissions"""

    class Meta:
        managed = False
        default_permissions = ()
        permissions = (
            ("basic_access", "Can access the moonmining app"),
            ("extractions_access", "Can access extractions and view owned moons"),
            ("reports_access", "Can access reports"),
            ("view_all_moons", "Can view all known moons"),
            ("upload_moon_scan", "Can upload moon scans"),
            ("add_refinery_owner", "Can add refinery owner"),
            ("view_moon_ledgers", "Can view moon ledgers"),
        )


class MiningLedgerRecord(models.Model):
    """A recorded mining activity in the vicinity of a refinery."""

    refinery = models.ForeignKey(
        "Refinery",
        on_delete=models.CASCADE,
        related_name="mining_ledger",
        help_text=_("Refinery this mining activity was observed at"),
    )
    day = models.DateField(db_index=True, help_text=_("last_updated in ESI"))
    character = models.ForeignKey(
        EveEntity,
        on_delete=models.CASCADE,
        related_name="+",
        help_text=_("character that did the mining"),
    )
    ore_type = models.ForeignKey(
        EveOreType, on_delete=models.CASCADE, related_name="mining_ledger"
    )
    # regular
    corporation = models.ForeignKey(
        EveEntity,
        on_delete=models.CASCADE,
        related_name="+",
        help_text=_("corporation of the character at time data was recorded"),
    )
    quantity = models.PositiveBigIntegerField()
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        default=None,
        null=True,
        related_name="mining_ledger",
    )

    objects = MiningLedgerRecordManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["refinery", "day", "character", "ore_type"],
                name="functional_pk_mining_activity",
            )
        ]
        verbose_name = _("ledger record")
        verbose_name_plural = _("ledger records")


class Moon(models.Model):
    """Known moon through either survey data or anchored refinery.

    "Head" model for many of the other models.
    """

    # pk
    eve_moon = models.OneToOneField(
        EveMoon, on_delete=models.CASCADE, primary_key=True, related_name="+"
    )
    # regular
    label = models.ForeignKey(
        Label, on_delete=models.SET_DEFAULT, default=None, null=True
    )
    products_updated_at = models.DateTimeField(
        null=True, default=None, help_text=_("Time the last moon survey was uploaded")
    )
    products_updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_DEFAULT,
        null=True,
        default=None,
        help_text=_("User who uploaded the last moon survey"),
    )
    rarity_class = models.PositiveIntegerField(
        choices=OreRarityClass.choices, default=OreRarityClass.NONE
    )
    value = models.FloatField(
        null=True,
        default=None,
        validators=[MinValueValidator(0.0)],
        db_index=True,
        help_text=_("Calculated value estimate"),
    )

    objects = MoonManager()

    class Meta:
        verbose_name = _("moon")
        verbose_name_plural = _("moons")

    def __str__(self):
        return self.name

    @property
    def name(self) -> str:
        return self.eve_moon.name.replace("Moon ", "")

    def region(self) -> str:
        return self.solar_system().eve_constellation.eve_region

    def solar_system(self) -> str:
        return self.eve_moon.eve_planet.eve_solar_system

    @property
    def is_owned(self) -> bool:
        return hasattr(self, "refinery")

    @property
    def rarity_tag_html(self) -> str:
        return OreRarityClass(self.rarity_class).bootstrap_tag_html

    def labels_html(self) -> str:
        """Generate HTML with all labels."""
        tags = [self.rarity_tag_html]
        if self.label:
            tags.append(self.label.tag_html)
        return format_html(" ".join(tags))

    def products_sorted(self) -> models.QuerySet:
        """Return current products as sorted iterable."""
        try:
            return (
                self.products.select_related(
                    "ore_type", "ore_type__eve_group", "ore_type__extras"
                )
                .annotate(total_price=self._total_price_db_func())
                .order_by("ore_type__name")
            )
        except (ObjectDoesNotExist, AttributeError):
            return type(self).objects.none()

    def calc_rarity_class(self) -> Optional[OreRarityClass]:
        try:
            return max(
                [
                    OreRarityClass.from_eve_group_id(eve_group_id)
                    for eve_group_id in self.products.select_related(
                        "ore_type"
                    ).values_list("ore_type__eve_group_id", flat=True)
                ]
            )
        except (ObjectDoesNotExist, ValueError):
            return OreRarityClass.NONE

    def calc_value(self) -> Optional[float]:
        """Calculate value estimate."""
        try:
            return self.products.aggregate(total_value=self._total_price_db_func())[
                "total_value"
            ]
        except (ObjectDoesNotExist, KeyError, AttributeError):
            return None

    @staticmethod
    def _total_price_db_func():
        return Sum(
            Coalesce(F("ore_type__extras__current_price"), 0.0)
            * F("amount")
            * Value(float(MOONMINING_VOLUME_PER_MONTH))
            / F("ore_type__volume"),
            output_field=models.FloatField(),
        )

    def update_calculated_properties(self):
        """Update all calculated properties for this moon."""
        self.value = self.calc_value()
        self.rarity_class = self.calc_rarity_class()
        self.save()

    def update_products(
        self, moon_products: List["MoonProduct"], updated_by: Optional[User] = None
    ) -> None:
        """Update products of this moon."""
        with transaction.atomic():
            self.products.all().delete()
            MoonProduct.objects.bulk_create(moon_products, batch_size=500)
        self.products_updated_at = now()
        self.products_updated_by = updated_by
        self.update_calculated_properties()

    def update_products_from_calculated_extraction(
        self, extraction: CalculatedExtraction, overwrite_survey: bool = False
    ) -> bool:
        """Replace moon product with calculated values from this extraction.

        Returns True if update was done, else False
        """
        if extraction.products and (
            overwrite_survey or self.products_updated_by is None
        ):
            moon_products = [
                MoonProduct(
                    moon=self,
                    amount=product.amount,
                    ore_type=EveOreType.objects.get_or_create_esi(
                        id=product.ore_type_id
                    )[0],
                )
                for product in extraction.moon_products_estimated(
                    MOONMINING_VOLUME_PER_DAY
                )
            ]
            self.update_products(moon_products)
            return True
        return False

    def update_products_from_latest_extraction(
        self, overwrite_survey: bool = False
    ) -> Optional[bool]:
        try:
            extraction = self.refinery.extractions.order_by("-started_at").first()
        except ObjectDoesNotExist:
            return None
        if not extraction:
            return None
        calculated_extraction = extraction.to_calculated_extraction()
        return self.update_products_from_calculated_extraction(
            calculated_extraction, overwrite_survey=overwrite_survey
        )


class MoonProduct(models.Model):
    """A product of a moon, i.e. a specific ore."""

    moon = models.ForeignKey(Moon, on_delete=models.CASCADE, related_name="products")
    ore_type = models.ForeignKey(EveOreType, on_delete=models.CASCADE, related_name="+")

    amount = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )

    def __str__(self):
        return f"{self.ore_type.name} - {self.amount}"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["moon", "ore_type"], name="functional_pk_moonproduct"
            )
        ]
        verbose_name = _("moon product")
        verbose_name_plural = _("moons products")

    @property
    def amount_percent(self) -> float:
        """Return the amount of this product as percent"""
        return self.amount * 100


class Notification(models.Model):
    """An EVE Online notification about structures."""

    # pk
    owner = models.ForeignKey(
        "Owner",
        on_delete=models.CASCADE,
        related_name="notifications",
        help_text=_("Corporation that received this notification"),
    )
    notification_id = models.PositiveBigIntegerField(verbose_name="id")
    # regular
    created = models.DateTimeField(
        null=True,
        default=None,
        help_text=_("Date when this notification was first received from ESI"),
    )
    details = models.JSONField(default=dict)
    notif_type = models.CharField(
        max_length=100,
        default="",
        db_index=True,
        verbose_name="type",
        help_text=_("type of this notification as reported by ESI"),
    )
    is_read = models.BooleanField(
        null=True,
        default=None,
        help_text=_("True when this notification has read in the eve client"),
    )
    last_updated = models.DateTimeField(
        help_text=_("Date when this notification has last been updated from ESI")
    )
    sender = models.ForeignKey(
        EveEntity, on_delete=models.CASCADE, null=True, default=None, related_name="+"
    )
    timestamp = models.DateTimeField(db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "notification_id"], name="functional_pk_notification"
            )
        ]
        verbose_name = _("notification")
        verbose_name_plural = _("notifications")

    def __str__(self) -> str:
        return str(self.notification_id)

    def __repr__(self) -> str:
        return "%s(notification_id=%s, owner='%s', notif_type='%s')" % (
            self.__class__.__name__,
            self.notification_id,
            self.owner,
            self.notif_type,
        )

    def to_calculated_extraction(self) -> CalculatedExtraction:
        """Generate a calculated extraction from this notification."""
        params = {"refinery_id": self.details["structureID"]}
        if self.notif_type == NotificationType.MOONMINING_EXTRACTION_STARTED:
            params.update(
                {
                    "status": CalculatedExtraction.Status.STARTED,
                    "chunk_arrival_at": ldap_time_2_datetime(self.details["readyTime"]),
                    "auto_fracture_at": ldap_time_2_datetime(self.details["autoTime"]),
                    "started_at": self.timestamp,
                    "started_by": self.details.get("startedBy"),
                    "products": CalculatedExtractionProduct.create_list_from_dict(
                        self.details["oreVolumeByType"]
                    ),
                }
            )
        elif self.notif_type == NotificationType.MOONMINING_EXTRACTION_FINISHED:
            params.update(
                {
                    "status": CalculatedExtraction.Status.READY,
                    "auto_fracture_at": ldap_time_2_datetime(self.details["autoTime"]),
                    "products": CalculatedExtractionProduct.create_list_from_dict(
                        self.details["oreVolumeByType"]
                    ),
                }
            )
        elif (
            self.notif_type == NotificationType.MOONMINING_LASER_FIRED
            or self.notif_type == NotificationType.MOONMINING_AUTOMATIC_FRACTURE
        ):
            params.update(
                {
                    "fractured_by": self.details.get("firedBy"),
                    "fractured_at": self.timestamp,
                    "status": CalculatedExtraction.Status.COMPLETED,
                    "products": CalculatedExtractionProduct.create_list_from_dict(
                        self.details["oreVolumeByType"]
                    ),
                }
            )
        elif self.notif_type == NotificationType.MOONMINING_EXTRACTION_CANCELLED:
            params.update(
                {
                    "status": CalculatedExtraction.Status.CANCELED,
                    "canceled_at": self.timestamp,
                    "canceled_by": self.details.get("cancelledBy"),
                }
            )
        return CalculatedExtraction(**params)


class Owner(models.Model):
    """A EVE Online corporation owning refineries."""

    ESI_SERVICE_NAME_MOON_DRILLING = "Moon Drilling"

    # pk
    corporation = models.OneToOneField(
        EveCorporationInfo, on_delete=models.CASCADE, primary_key=True, related_name="+"
    )
    # regular
    character_ownership = models.ForeignKey(
        CharacterOwnership,
        on_delete=models.SET_DEFAULT,
        default=None,
        null=True,
        related_name="+",
        help_text=_("Character used to sync this corporation from ESI"),
    )
    is_enabled = models.BooleanField(
        default=True,
        db_index=True,
        help_text=_("Disabled corporations are excluded from the update process"),
    )
    last_update_at = models.DateTimeField(
        null=True, default=None, help_text=_("Time of last successful update")
    )
    last_update_ok = models.BooleanField(
        null=True, default=None, help_text=_("True if the last update was successful")
    )

    class Meta:
        verbose_name = _("owner")
        verbose_name_plural = _("owners")

    def __str__(self):
        return self.name

    @property
    def name(self) -> str:
        alliance_ticker_str = (
            f" [{self.corporation.alliance.alliance_ticker}]"
            if self.corporation.alliance
            else ""
        )
        return f"{self.corporation}{alliance_ticker_str}"

    @property
    def alliance_name(self) -> str:
        return (
            self.corporation.alliance.alliance_name if self.corporation.alliance else ""
        )

    @property
    def name_html(self):
        return bootstrap_icon_plus_name_html(
            self.corporation.logo_url(size=IconSize.SMALL),
            self.name,
            size=IconSize.SMALL,
        )

    def fetch_token(self) -> Token:
        """Return valid token for this mining corp or raise exception on any error."""
        if not self.character_ownership:
            raise RuntimeError("This owner has no character configured.")
        token = (
            Token.objects.filter(
                character_id=self.character_ownership.character.character_id
            )
            .require_scopes(self.esi_scopes())
            .require_valid()
            .first()
        )
        if not token:
            raise Token.DoesNotExist(f"{self}: No valid token found.")
        return token

    def update_refineries_from_esi(self):
        """Update all refineries from ESI."""
        logger.info("%s: Updating refineries...", self)
        refineries = self._fetch_refineries_from_esi()
        for structure_id in refineries.keys():
            try:
                self._update_or_create_refinery_from_esi(structure_id)
            except OSError as exc:
                exc_name = type(exc).__name__
                msg = (
                    f"{self}: Failed to fetch refinery with ID {structure_id} from ESI"
                )
                message_id = (
                    f"{__title__}-update_refineries_from_esi-"
                    f"{structure_id}-{exc_name}"
                )
                notify_admins_throttled(
                    message_id=message_id,
                    message=f"{msg}: {exc_name}: {exc}.",
                    title=f"{__title__}: Failed to fetch refinery",
                    level="warning",
                )
                logger.warning(msg, exc_info=True)
        # remove refineries that no longer exist
        self.refineries.exclude(id__in=refineries).delete()

        self.last_update_at = now()
        self.save()

    def _fetch_refineries_from_esi(self) -> dict:
        """Return current refineries with moon drills from ESI for this owner."""
        logger.info("%s: Fetching refineries from ESI...", self)
        structures = esi.client.Corporation.get_corporations_corporation_id_structures(
            corporation_id=self.corporation.corporation_id,
            token=self.fetch_token().valid_access_token(),
        ).results()
        refineries = dict()
        for structure_info in structures:
            eve_type, _ = EveType.objects.get_or_create_esi(
                id=structure_info["type_id"]
            )
            structure_info["_eve_type"] = eve_type
            service_names = (
                {row["name"] for row in structure_info["services"]}
                if structure_info.get("services")
                else set()
            )
            if (
                eve_type.eve_group_id == EveGroupId.REFINERY
                and self.ESI_SERVICE_NAME_MOON_DRILLING in service_names
            ):
                refineries[structure_info["structure_id"]] = structure_info
        return refineries

    def _update_or_create_refinery_from_esi(self, structure_id: int):
        """Update or create a refinery with universe data from ESI."""
        logger.info("%s: Fetching details for refinery #%d", self, structure_id)
        structure_info = esi.client.Universe.get_universe_structures_structure_id(
            structure_id=structure_id, token=self.fetch_token().valid_access_token()
        ).results()
        refinery, _ = Refinery.objects.update_or_create(
            id=structure_id,
            defaults={
                "name": structure_info["name"],
                "eve_type": EveType.objects.get(id=structure_info["type_id"]),
                "owner": self,
            },
        )
        if not refinery.moon:
            refinery.update_moon_from_structure_info(structure_info)
        return True

    def fetch_notifications_from_esi(self) -> None:
        """fetches notification for the current owners and process them"""
        notifications = self._fetch_moon_notifications_from_esi()
        self._store_notifications(notifications)

    def _fetch_moon_notifications_from_esi(self) -> List[dict]:
        """Fetch all notifications from ESI for current owner."""
        logger.info("%s: Fetching notifications from ESI...", self)
        all_notifications = (
            esi.client.Character.get_characters_character_id_notifications(
                character_id=self.character_ownership.character.character_id,
                token=self.fetch_token().valid_access_token(),
            ).results()
        )
        moon_notifications = [
            notif
            for notif in all_notifications
            if notif["type"] in NotificationType.all_moon_mining
        ]
        return moon_notifications

    def _store_notifications(self, notifications: list) -> int:
        """Store new notifications in database and return count of new objects."""
        # identify new notifications
        existing_notification_ids = set(
            self.notifications.values_list("notification_id", flat=True)
        )
        new_notifications = [
            obj
            for obj in notifications
            if obj["notification_id"] not in existing_notification_ids
        ]
        # create new notif objects
        sender_type_map = {
            "character": EveEntity.CATEGORY_CHARACTER,
            "corporation": EveEntity.CATEGORY_CORPORATION,
            "alliance": EveEntity.CATEGORY_ALLIANCE,
        }
        new_notification_objects = list()
        for notification in new_notifications:
            known_sender_type = sender_type_map.get(notification["sender_type"])
            if known_sender_type:
                sender, _ = EveEntity.objects.get_or_create_esi(
                    id=notification["sender_id"]
                )
            else:
                sender = None
            text = notification["text"] if "text" in notification else None
            is_read = notification["is_read"] if "is_read" in notification else None
            new_notification_objects.append(
                Notification(
                    notification_id=notification["notification_id"],
                    owner=self,
                    created=now(),
                    details=yaml.safe_load(text) if text else {},
                    is_read=is_read,
                    last_updated=now(),
                    # at least one type has a trailing white space
                    # which we need to remove
                    notif_type=notification["type"].strip(),
                    sender=sender,
                    timestamp=notification["timestamp"],
                )
            )

        Notification.objects.bulk_create(new_notification_objects)
        if len(new_notification_objects) > 0:
            logger.info(
                "%s: Received %d new notifications from ESI",
                self,
                len(new_notification_objects),
            )
        else:
            logger.info("%s: No new notifications received from ESI", self)
        return len(new_notification_objects)

    def update_extractions(self):
        self.update_extractions_from_esi()
        Extraction.objects.all().update_status()
        self.update_extractions_from_notifications()

    def update_extractions_from_esi(self):
        """Creates new extractions from ESI for current owner."""
        extractions_by_refinery = self._fetch_extractions_from_esi()
        self._update_or_create_extractions(extractions_by_refinery)

    def _fetch_extractions_from_esi(self):
        logger.info("%s: Fetching extractions from ESI...", self)
        extractions = (
            esi.client.Industry.get_corporation_corporation_id_mining_extractions(
                corporation_id=self.corporation.corporation_id,
                token=self.fetch_token().valid_access_token(),
            ).results()
        )
        logger.info("%s: Received %d extractions from ESI.", self, len(extractions))
        extractions_by_refinery = defaultdict(list)
        for row in extractions:
            extractions_by_refinery[row["structure_id"]].append(row)
        return extractions_by_refinery

    def _update_or_create_extractions(self, extractions_by_refinery: dict) -> None:
        new_extractions_count = 0
        for refinery_id, refinery_extractions in extractions_by_refinery.items():
            try:
                refinery = self.refineries.get(pk=refinery_id)
            except Refinery.DoesNotExist:
                continue
            new_extractions_count += refinery.create_extractions_from_esi_response(
                refinery_extractions
            )
            refinery.cancel_started_extractions_missing_from_list(
                [row["extraction_start_time"] for row in refinery_extractions]
            )
        if new_extractions_count:
            logger.info("%s: Created %d new extractions.", self, new_extractions_count)

    def update_extractions_from_notifications(self):
        """Add information from notifications to extractions."""
        logger.info("%s: Updating extractions from notifications...", self)
        notifications_count = self.notifications.count()
        if not notifications_count:
            logger.info("%s: No moon notifications.", self)
            return
        logger.info("%s: Processing %d moon notifications.", self, notifications_count)

        # create or update extractions from notifications by refinery
        for refinery in self.refineries.all():
            updated_count = 0
            extraction = None
            notifications_for_refinery = self.notifications.filter(
                details__structureID=refinery.id
            )
            if not refinery.moon and notifications_for_refinery.exists():
                # Update the refinery's moon from notification in case
                # it was not found by nearest_celestial.
                notif = notifications_for_refinery.first()
                refinery.update_moon_from_eve_id(notif.details["moonID"])
            for notif in notifications_for_refinery.order_by("timestamp"):
                if notif.notif_type == NotificationType.MOONMINING_EXTRACTION_STARTED:
                    extraction = notif.to_calculated_extraction()
                    if refinery.moon.update_products_from_calculated_extraction(
                        extraction,
                        overwrite_survey=MOONMINING_OVERWRITE_SURVEYS_WITH_ESTIMATES,
                    ):
                        logger.info(
                            "%s: Products updated from extraction", refinery.moon
                        )

                elif extraction:
                    if extraction.status == CalculatedExtraction.Status.STARTED:
                        if (
                            notif.notif_type
                            == NotificationType.MOONMINING_EXTRACTION_CANCELLED
                        ):
                            extraction.status = CalculatedExtraction.Status.CANCELED
                            extraction.canceled_at = notif.timestamp
                            extraction.canceled_by = notif.details.get("cancelledBy")
                            updated = Extraction.objects.update_from_calculated(
                                extraction
                            )
                            updated_count += 1 if updated else 0
                            extraction = None

                        elif (
                            notif.notif_type
                            == NotificationType.MOONMINING_EXTRACTION_FINISHED
                        ):
                            extraction.status = CalculatedExtraction.Status.READY
                            extraction.products = (
                                CalculatedExtractionProduct.create_list_from_dict(
                                    notif.details["oreVolumeByType"]
                                )
                            )

                    elif extraction.status == CalculatedExtraction.Status.READY:
                        if notif.notif_type == NotificationType.MOONMINING_LASER_FIRED:
                            extraction.status = CalculatedExtraction.Status.COMPLETED
                            extraction.fractured_at = notif.timestamp
                            extraction.fractured_by = notif.details.get("firedBy")
                            extraction.products = (
                                CalculatedExtractionProduct.create_list_from_dict(
                                    notif.details["oreVolumeByType"]
                                )
                            )
                            updated = Extraction.objects.update_from_calculated(
                                extraction
                            )
                            updated_count += 1 if updated else 0
                            extraction = None

                        elif (
                            notif.notif_type
                            == NotificationType.MOONMINING_AUTOMATIC_FRACTURE
                        ):
                            extraction.status = CalculatedExtraction.Status.COMPLETED
                            extraction.fractured_at = notif.timestamp
                            extraction.products = (
                                CalculatedExtractionProduct.create_list_from_dict(
                                    notif.details["oreVolumeByType"]
                                )
                            )
                            updated = Extraction.objects.update_from_calculated(
                                extraction
                            )
                            updated_count += 1 if updated else 0
                            extraction = None
                else:
                    if (
                        notif.notif_type
                        == NotificationType.MOONMINING_EXTRACTION_FINISHED
                    ):
                        extraction = notif.to_calculated_extraction()

            if extraction:
                updated = Extraction.objects.update_from_calculated(extraction)
                updated_count += 1 if updated else 0
            if updated_count:
                logger.info(
                    "%s: %s: Updated %d extractions from notifications",
                    self,
                    refinery,
                    updated_count,
                )

    def fetch_mining_ledger_observers_from_esi(self) -> set:
        logger.info("%s: Fetching mining observers from ESI...", self)
        observers = esi.client.Industry.get_corporation_corporation_id_mining_observers(
            corporation_id=self.corporation.corporation_id,
            token=self.fetch_token().valid_access_token(),
        ).results()
        logger.info("%s: Received %d observers from ESI.", self, len(observers))
        return {
            row["observer_id"]
            for row in observers
            if row["observer_type"] == "structure"
        }

    @classmethod
    def esi_scopes(cls):
        """Return list of all required esi scopes."""
        return [
            "esi-industry.read_corporation_mining.v1",
            "esi-universe.read_structures.v1",
            "esi-characters.read_notifications.v1",
            "esi-corporations.read_structures.v1",
            "esi-industry.read_corporation_mining.v1",
        ]


class Refinery(models.Model):
    """An Eve Online refinery structure."""

    # pk
    id = models.PositiveBigIntegerField(primary_key=True)
    # regular
    eve_type = models.ForeignKey(EveType, on_delete=models.CASCADE, related_name="+")
    moon = models.OneToOneField(
        Moon,
        on_delete=models.SET_DEFAULT,
        default=None,
        null=True,
        related_name="refinery",
        help_text=_("The moon this refinery is anchored at (if any)"),
    )
    name = models.CharField(max_length=150, db_index=True)
    owner = models.ForeignKey(
        Owner,
        on_delete=models.CASCADE,
        related_name="refineries",
        help_text=_("Corporation that owns this refinery"),
    )
    ledger_last_update_at = models.DateTimeField(
        null=True, default=None, help_text=_("last successful update of mining ledger")
    )
    ledger_last_update_ok = models.BooleanField(
        null=True,
        default=None,
        help_text=_("True if the last update of the mining ledger was successful"),
    )

    objects = RefineryManager()

    class Meta:
        verbose_name = _("refinery")
        verbose_name_plural = _("refineries")

    def __str__(self):
        return self.name

    def name_html(self) -> str:
        return format_html("{}<br>{}", self.name, self.owner.name)

    def update_moon_from_structure_info(self, structure_info: dict) -> bool:
        """Find moon based on location in space and update the object.
        Returns True when successful, else false
        """
        solar_system, _ = EveSolarSystem.objects.get_or_create_esi(
            id=structure_info["solar_system_id"]
        )
        try:
            nearest_celestial = solar_system.nearest_celestial(
                x=structure_info["position"]["x"],
                y=structure_info["position"]["y"],
                z=structure_info["position"]["z"],
                group_id=EveGroupId.MOON,
            )
        except OSError:
            logger.exception("%s: Failed to fetch nearest celestial ", self)
            return False
        if not nearest_celestial or nearest_celestial.eve_type.id != EveTypeId.MOON:
            return False
        eve_moon = nearest_celestial.eve_object
        moon, _ = Moon.objects.get_or_create(eve_moon=eve_moon)
        self.moon = moon
        self.save()
        return True

    def update_moon_from_eve_id(self, eve_moon_id: int):
        eve_moon, _ = EveMoon.objects.get_or_create_esi(id=eve_moon_id)
        moon, _ = Moon.objects.get_or_create(eve_moon=eve_moon)
        self.moon = moon
        self.save()

    def update_mining_ledger_from_esi(self):
        logger.debug("%s: Fetching mining observer records from ESI...", self)
        self.ledger_last_update_at = now()
        self.ledger_last_update_ok = None
        self.save()
        records = esi.client.Industry.get_corporation_corporation_id_mining_observers_observer_id(
            corporation_id=self.owner.corporation.corporation_id,
            observer_id=self.id,
            token=self.owner.fetch_token().valid_access_token(),
        ).results()
        logger.info(
            "%s: Received %d mining observer records from ESI", self, len(records)
        )
        # preload all missing ore types
        EveOreType.objects.bulk_get_or_create_esi(
            ids=[record["type_id"] for record in records]
        )
        character_2_user = {
            obj[0]: obj[1]
            for obj in CharacterOwnership.objects.values_list(
                "character__character_id",
                "user_id",
            )
        }
        for record in records:
            character, _ = EveEntity.objects.get_or_create(id=record["character_id"])
            corporation, _ = EveEntity.objects.get_or_create(
                id=record["recorded_corporation_id"]
            )
            MiningLedgerRecord.objects.update_or_create(
                refinery=self,
                character=character,
                day=record["last_updated"],
                ore_type_id=record["type_id"],
                defaults={
                    "corporation": corporation,
                    "quantity": record["quantity"],
                    "user_id": character_2_user.get(character.id),
                },
            )
        EveEntity.objects.bulk_update_new_esi()
        self.ledger_last_update_ok = True
        self.save()

    def create_extractions_from_esi_response(self, esi_extractions: List[dict]) -> int:
        existing_extractions = set(
            self.extractions.values_list("started_at", flat=True)
        )
        new_extractions = list()
        for esi_extraction in esi_extractions:
            extraction_start_time = esi_extraction["extraction_start_time"]
            if extraction_start_time not in existing_extractions:
                chunk_arrival_time = esi_extraction["chunk_arrival_time"]
                auto_fracture_at = esi_extraction["natural_decay_time"]
                if now() > auto_fracture_at:
                    status = Extraction.Status.COMPLETED
                elif now() > chunk_arrival_time:
                    status = Extraction.Status.READY
                else:
                    status = Extraction.Status.STARTED
                new_extractions.append(
                    Extraction(
                        refinery=self,
                        chunk_arrival_at=esi_extraction["chunk_arrival_time"],
                        started_at=extraction_start_time,
                        status=status,
                        auto_fracture_at=auto_fracture_at,
                    )
                )
        if new_extractions:
            Extraction.objects.bulk_create(new_extractions, batch_size=500)
        return len(new_extractions)

    def cancel_started_extractions_missing_from_list(
        self, started_at_list: List[dt.datetime]
    ) -> int:
        """Cancel started extractions that are not included in given list."""
        canceled_extractions_qs = self.extractions.filter(
            status=Extraction.Status.STARTED
        ).exclude(started_at__in=started_at_list)
        canceled_extractions_count = canceled_extractions_qs.count()
        if canceled_extractions_count:
            logger.info(
                "%s: Found %d likely canceled extractions.",
                self,
                canceled_extractions_count,
            )
            canceled_extractions_qs.update(
                status=Extraction.Status.CANCELED, canceled_at=now()
            )
        return canceled_extractions_count
