import datetime as dt
from collections import defaultdict
from enum import Enum
from typing import Iterable, List, Optional

import yaml

from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.functional import cached_property, classproperty
from django.utils.timezone import now
from esi.models import Token
from eveuniverse.models import EveEntity, EveMoon, EveSolarSystem, EveType

from allianceauth.authentication.models import CharacterOwnership
from allianceauth.eveonline.models import EveCorporationInfo
from allianceauth.services.hooks import get_extension_logger
from app_utils.datetime import ldap_time_2_datetime
from app_utils.logging import LoggerAddTag
from app_utils.views import (
    BootstrapStyle,
    bootstrap_icon_plus_name_html,
    bootstrap_label_html,
)

from . import __title__, constants
from .app_settings import MOONMINING_REPROCESSING_YIELD, MOONMINING_VOLUME_PER_MONTH
from .core import CalculatedExtraction, CalculatedExtractionProduct
from .managers import (
    EveOreTypeManger,
    ExtractionManager,
    MiningLedgerRecordManager,
    MoonManager,
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


class OreRarityClass(models.IntegerChoices):
    """Rarity class of an ore"""

    NONE = 0, ""
    R4 = 4, "R4"
    R8 = 8, "R8"
    R16 = 16, "R16"
    R32 = 32, "R32"
    R64 = 64, "R64"

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
                f"R{self.value}", label=map_rarity_to_type[self.value]
            )
        except KeyError:
            return ""

    @classmethod
    def from_eve_group_id(cls, eve_group_id: int) -> "OreRarityClass":
        """Create object from eve group ID"""
        map_group_2_rarity = {
            constants.EVE_GROUP_ID_UBIQUITOUS_MOON_ASTEROIDS: cls.R4,
            constants.EVE_GROUP_ID_COMMON_MOON_ASTEROIDS: cls.R8,
            constants.EVE_GROUP_ID_UNCOMMON_MOON_ASTEROIDS: cls.R16,
            constants.EVE_GROUP_ID_RARE_MOON_ASTEROIDS: cls.R32,
            constants.EVE_GROUP_ID_EXCEPTIONAL_MOON_ASTEROIDS: cls.R64,
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

    UNDEFINED = "UN", "(undefined)"
    REGULAR = "RE", "regular"
    IMPROVED = "IM", "improved"
    EXCELLENT = "EX", "excellent"

    @property
    def bootstrap_tag_html(self) -> str:
        """Return bootstrap tag."""
        map_quality_to_label_def = {
            self.IMPROVED: {"text": "+15%", "label": BootstrapStyle.SUCCESS},
            self.EXCELLENT: {"text": "+100%", "label": BootstrapStyle.WARNING},
        }
        try:
            label_def = map_quality_to_label_def[self.value]
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
                eve_dogma_attribute_id=constants.DOGMA_ATTRIBUTE_ID_ORE_QUALITY
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

    URL_PROFILE_TYPE = "https://www.kalkoken.org/apps/eveitems/"

    class Meta:
        proxy = True

    objects = EveOreTypeManger()

    @property
    def profile_url(self) -> str:
        return f"{self.URL_PROFILE_TYPE}?typeId={self.id}"

    def calc_refined_value_by_volume(
        self, volume: float, reprocessing_yield: float = None
    ) -> float:
        """Calculate the refined total value for given volume and return it."""
        if not reprocessing_yield:
            reprocessing_yield = MOONMINING_REPROCESSING_YIELD
        if not self.volume:
            return 0
        volume_per_unit = self.volume
        units = volume / volume_per_unit
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
        return value

    def calc_refined_value_per_unit(self, reprocessing_yield: float = None) -> float:
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

        # EveOreType.objects.annotate(extras=Sum(F("materials__quantity") * Value(0.81) * F("materials__material_eve_type__market_price__average_price") / Value(100), output_field=FloatField())).get(id=45506).extras

    @property
    def icon_url_32(self) -> str:
        return self.icon_url(32)

    @property
    def rarity_class(self) -> OreRarityClass:
        return OreRarityClass.from_eve_type(self)

    @cached_property
    def quality_class(self) -> OreQualityClass:
        return OreQualityClass.from_eve_type(self)

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
    """Extra fields for an EveOreType."""

    ore_type = models.OneToOneField(
        EveOreType, on_delete=models.CASCADE, related_name="extras"
    )
    refined_price = models.FloatField(
        default=None,
        null=True,
        help_text="price calculated as sum of prices for refined materials",
    )

    def __str__(self) -> str:
        return str(self.ore_type)


class ProductsSortedMixin:
    @cached_property
    def products_sorted(self):
        """Return current products as sorted iterable."""
        try:
            return self.products.select_related(
                "ore_type", "ore_type__eve_group", "ore_type__extras"
            ).order_by("-ore_type__eve_group_id")
        except ObjectDoesNotExist:
            return type(self).objects.none()


class Extraction(models.Model, ProductsSortedMixin):
    """A mining extraction."""

    class Status(models.TextChoices):
        STARTED = "ST", "started"  # has been started
        CANCELED = "CN", "canceled"  # has been canceled
        READY = "RD", "ready"  # has finished extraction and is ready to be fractured
        COMPLETED = "CP", "completed"  # has been fractured
        UNDEFINED = "UN", "undefined"  # unclear status

        @property
        def bootstrap_tag_html(self) -> str:
            map_to_type = {
                self.STARTED: BootstrapStyle.SUCCESS,
                self.CANCELED: BootstrapStyle.DANGER,
                self.READY: BootstrapStyle.WARNING,
                self.COMPLETED: BootstrapStyle.DEFAULT,
                self.UNDEFINED: "",
            }
            try:
                return bootstrap_label_html(self.label, label=map_to_type[self.value])
            except KeyError:
                return ""

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
    started_at = models.DateTimeField(help_text="when this extraction was started")
    # normal properties
    auto_fracture_at = models.DateTimeField(
        help_text="when this extraction will be automatically fractured",
    )
    canceled_at = models.DateTimeField(
        null=True, default=None, help_text="when this extraction was canceled"
    )
    canceled_by = models.ForeignKey(
        EveEntity,
        on_delete=models.SET_DEFAULT,
        null=True,
        default=None,
        related_name="+",
        help_text="Eve character who canceled this extraction",
    )
    chunk_arrival_at = models.DateTimeField(
        db_index=True, help_text="when this extraction is ready to be fractured"
    )
    fractured_at = models.DateTimeField(
        null=True, default=None, help_text="when this extraction was fractured"
    )
    fractured_by = models.ForeignKey(
        EveEntity,
        on_delete=models.SET_DEFAULT,
        null=True,
        default=None,
        related_name="+",
        help_text="Eve character who fractured this extraction (if any)",
    )
    is_jackpot = models.BooleanField(
        default=None,
        null=True,
        help_text="Whether this is a jackpot extraction (calculated)",
    )
    started_by = models.ForeignKey(
        EveEntity,
        on_delete=models.SET_DEFAULT,
        null=True,
        default=None,
        related_name="+",
        help_text="Eve character who started this extraction",
    )
    status = models.CharField(
        max_length=2, choices=Status.choices, default=Status.UNDEFINED, db_index=True
    )
    value = models.FloatField(
        null=True,
        default=None,
        validators=[MinValueValidator(0.0)],
        help_text="Estimated value of this extraction (calculated)",
    )

    objects = ExtractionManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["refinery", "started_at"], name="functional_pk_extraction"
            )
        ]

    def __str__(self) -> str:
        return f"{self.refinery} - {self.started_at} - {self.status}"

    @property
    def status_enum(self) -> "Extraction.Status":
        """Return current status as enum type."""
        return self.Status(self.status)

    @cached_property
    def ledger(self) -> models.QuerySet:
        """Return ledger for this extraction."""
        max_day = self.chunk_arrival_at + dt.timedelta(days=6)
        return self.refinery.mining_ledger.filter(
            day__gte=self.chunk_arrival_at,
            day__lte=max_day,
        )

    def calc_value(self) -> Optional[float]:
        """Calculate value estimate and return result."""
        try:
            return sum(
                [
                    product.calc_value()
                    for product in self.products.select_related("ore_type")
                ]
            )
        except ObjectDoesNotExist:
            return None

    def calc_is_jackpot(self) -> Optional[bool]:
        """Calculate if extraction is jackpot and return result.
        Return None if extraction has no products"""
        try:
            products_qualities = [
                product.ore_type.quality_class == OreQualityClass.EXCELLENT
                for product in self.products.select_related("ore_type").all()
            ]
        except ObjectDoesNotExist:
            return None
        else:
            if not products_qualities:
                return None
            return all(products_qualities)

    def update_calculated_properties(self) -> float:
        """Update calculated properties for this extraction."""
        self.value = self.calc_value()
        self.is_jackpot = self.calc_is_jackpot()
        self.save()


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

    def __str__(self) -> str:
        return f"{self.extraction} - {self.ore_type}"

    @cached_property
    def value(self) -> float:
        return self.calc_value()

    def calc_value(self, reprocessing_yield=None) -> float:
        """returns calculated value estimate in ISK

        Args:
            reprocessing_yield: expected average yield for ore reprocessing
        Returns:
            value estimate or None if prices are missing

        """
        return self.ore_type.calc_refined_value_by_volume(
            volume=self.volume, reprocessing_yield=reprocessing_yield
        )


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
        )


class MiningLedgerRecord(models.Model):
    """A recorded mining activity in the vicinity of a refinery."""

    # pk
    refinery = models.ForeignKey(
        "Refinery",
        on_delete=models.CASCADE,
        related_name="mining_ledger",
        help_text="Refinery this mining activity was observed at",
    )
    day = models.DateField(help_text="last_updated in ESI", db_index=True)
    character = models.ForeignKey(
        EveEntity,
        on_delete=models.CASCADE,
        related_name="+",
        help_text="character that did the mining",
    )
    ore_type = models.ForeignKey(
        EveOreType, on_delete=models.CASCADE, related_name="mining_ledger"
    )
    # regular
    corporation = models.ForeignKey(
        EveEntity,
        on_delete=models.CASCADE,
        related_name="+",
        help_text="corporation of the character at time data was recorded",
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


class Moon(models.Model, ProductsSortedMixin):
    """Known moon through either survey data or anchored refinery.

    "Head" model for many of the other models
    """

    # pk
    eve_moon = models.OneToOneField(
        EveMoon, on_delete=models.CASCADE, primary_key=True, related_name="known_moon"
    )
    # regular
    products_updated_at = models.DateTimeField(
        null=True, default=None, help_text="Time the last moon survey was uploaded"
    )
    products_updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_DEFAULT,
        null=True,
        default=None,
        help_text="User who uploaded the last moon survey",
    )
    rarity_class = models.PositiveIntegerField(
        choices=OreRarityClass.choices, default=OreRarityClass.NONE
    )
    value = models.FloatField(
        null=True,
        default=None,
        validators=[MinValueValidator(0.0)],
        db_index=True,
        help_text="Calculated value estimate",
    )

    objects = MoonManager()

    def __str__(self):
        return self.name

    @property
    def name(self) -> str:
        return self.eve_moon.name.replace("Moon ", "")

    @cached_property
    def region(self) -> str:
        return self.eve_moon.eve_planet.eve_solar_system.eve_constellation.eve_region

    @property
    def is_owned(self) -> bool:
        return hasattr(self, "refinery")

    @property
    def rarity_tag_html(self) -> str:
        return OreRarityClass(self.rarity_class).bootstrap_tag_html

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
            return sum(
                [
                    product.calc_value(total_volume=MOONMINING_VOLUME_PER_MONTH)
                    for product in self.products.select_related("ore_type")
                ]
            )
        except ObjectDoesNotExist:
            return None

    def update_calculated_properties(self):
        """Update all calculated properties for this moon."""
        self.value = self.calc_value()
        self.rarity_class = self.calc_rarity_class()
        self.save()


class MoonProduct(models.Model):
    """A product of a moon, i.e. a specifc ore."""

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

    @cached_property
    def value(self):
        """Return the calculated value for this product."""
        return self.calc_value()

    @property
    def amount_percent(self) -> float:
        """Return the amount of this product as percent"""
        return self.amount * 100

    def calc_value(self, total_volume=None, reprocessing_yield=None) -> float:
        """Return calculated value estimate for given parameters.

        Args:
            total_volume: total excepted ore volume for this moon
            reprocessing_yield: expected average yield for ore reprocessing

        Returns:
            value estimate for moon or None if prices or products are missing
        """
        if not total_volume:
            total_volume = MOONMINING_VOLUME_PER_MONTH
        return self.ore_type.calc_refined_value_by_volume(
            volume=total_volume * self.amount, reprocessing_yield=reprocessing_yield
        )


class Notification(models.Model):
    """An EVE Online notification about structures."""

    # pk
    owner = models.ForeignKey(
        "Owner",
        on_delete=models.CASCADE,
        related_name="notifications",
        help_text="Corporation that received this notification",
    )
    notification_id = models.PositiveBigIntegerField(verbose_name="id")
    # regular
    created = models.DateTimeField(
        null=True,
        default=None,
        help_text="Date when this notification was first received from ESI",
    )
    details = models.JSONField(default=dict)
    notif_type = models.CharField(
        max_length=100,
        default="",
        db_index=True,
        verbose_name="type",
        help_text="type of this notification as reported by ESI",
    )
    is_read = models.BooleanField(
        null=True,
        default=None,
        help_text="True when this notification has read in the eve client",
    )
    last_updated = models.DateTimeField(
        help_text="Date when this notification has last been updated from ESI"
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

    def __str__(self) -> str:
        return str(self.notification_id)

    def __repr__(self) -> str:
        return "%s(notification_id=%d, owner='%s', notif_type='%s')" % (
            self.__class__.__name__,
            self.notification_id,
            self.owner,
            self.notif_type,
        )


class Owner(models.Model):
    """A EVE Online corporation owning refineries."""

    # pk
    corporation = models.OneToOneField(
        EveCorporationInfo,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="mining_corporation",
    )
    # regular
    character_ownership = models.ForeignKey(
        CharacterOwnership,
        on_delete=models.SET_DEFAULT,
        default=None,
        null=True,
        related_name="+",
        help_text="character used to sync this corporation from ESI",
    )
    is_enabled = models.BooleanField(
        default=True,
        db_index=True,
        help_text="disabled corporations are excluded from the update process",
    )
    last_update_at = models.DateTimeField(
        null=True, default=None, help_text="time of last successful update"
    )
    last_update_ok = models.BooleanField(
        null=True, default=None, help_text="True if the last update was successful"
    )

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
            self.corporation.logo_url(size=constants.IconSize.SMALL),
            self.name,
            size=constants.IconSize.SMALL,
        )

    def fetch_token(self):
        """Fetch token for this mining corp and return it..."""
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
        return token

    def update_refineries_from_esi(self):
        """Update all refineries from ESI."""
        logger.info("%s: Updating refineries...", self)
        refineries = self._fetch_refineries_from_esi()
        for structure_id, _ in refineries.items():
            self._update_or_create_refinery_from_esi(structure_id)

        # remove refineries that no longer exist
        self.refineries.exclude(id__in=refineries).delete()

        self.last_update_at = now()
        self.save()

    def _fetch_refineries_from_esi(self) -> dict:
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
            if eve_type.eve_group_id == constants.EVE_GROUP_ID_REFINERY:
                refineries[structure_info["structure_id"]] = structure_info
        return refineries

    def _update_or_create_refinery_from_esi(self, structure_id: int):
        logger.info("%s: Fetching details for refinery #%d", self, structure_id)
        try:
            structure_info = esi.client.Universe.get_universe_structures_structure_id(
                structure_id=structure_id, token=self.fetch_token().valid_access_token()
            ).results()
        except OSError:
            logger.exception("%s: Failed to fetch refinery #%d", self, structure_id)
            return
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

    def fetch_notifications_from_esi(self) -> bool:
        """fetches notification for the current owners and proceses them"""
        notifications = self._fetch_moon_notifications_from_esi()
        self._store_notifications(notifications)

    def _fetch_moon_notifications_from_esi(self) -> dict:
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
                    details=yaml.safe_load(text),
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
                """Update the refinery's moon from notification in case
                it was not found by nearest_celestial.
                """
                notif = notifications_for_refinery.first()
                refinery.update_moon_from_eve_id(notif.details["moonID"])
            for notif in notifications_for_refinery.order_by("timestamp"):
                if notif.notif_type == NotificationType.MOONMINING_EXTRACTION_STARTED:
                    extraction = CalculatedExtraction(
                        refinery_id=refinery.id,
                        status=CalculatedExtraction.Status.STARTED,
                        chunk_arrival_at=ldap_time_2_datetime(
                            notif.details["readyTime"]
                        ),
                        auto_fracture_at=ldap_time_2_datetime(
                            notif.details["autoTime"]
                        ),
                        started_by=notif.details.get("startedBy"),
                        products=CalculatedExtractionProduct.create_list_from_dict(
                            notif.details["oreVolumeByType"]
                        ),
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
                        extraction = CalculatedExtraction(
                            refinery_id=refinery.id,
                            status=CalculatedExtraction.Status.READY,
                            auto_fracture_at=ldap_time_2_datetime(
                                notif.details["autoTime"]
                            ),
                            products=CalculatedExtractionProduct.create_list_from_dict(
                                notif.details["oreVolumeByType"]
                            ),
                        )

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
        help_text="The moon this refinery is anchored at (if any)",
    )
    name = models.CharField(max_length=150, db_index=True)
    owner = models.ForeignKey(
        Owner,
        on_delete=models.CASCADE,
        related_name="refineries",
        help_text="Corporation that owns this refinery",
    )
    ledger_last_update_at = models.DateTimeField(
        null=True, default=None, help_text="last successful update of mining ledger"
    )
    ledger_last_update_ok = models.BooleanField(
        null=True,
        default=None,
        help_text="True if the last update of the mining ledger was successful",
    )

    def __str__(self):
        return self.name

    def update_moon_from_structure_info(self, structure_info: dict) -> bool:
        """Find moon based on location in space and update the object.
        Returns True when successful, else false
        """
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
            logger.exception("%s: Failed to fetch nearest celestial ", self)
        else:
            if (
                nearest_celestial
                and nearest_celestial.eve_type.id == constants.EVE_TYPE_ID_MOON
            ):
                eve_moon = nearest_celestial.eve_object
                moon, _ = Moon.objects.get_or_create(eve_moon=eve_moon)
                self.moon = moon
                self.save()
                return True
        return False

    def update_moon_from_eve_id(self, eve_moon_id: int):
        eve_moon, _ = EveMoon.objects.get_or_create_esi(id=eve_moon_id)
        moon, _ = Moon.objects.get_or_create(eve_moon=eve_moon)
        self.moon = moon
        self.save()

    def update_mining_ledger_from_esi(self):
        logger.info("%s: Fetching mining observer records from ESI...", self)
        self.ledger_last_update_at = now()
        self.ledger_last_update_ok = None
        self.save()
        records = esi.client.Industry.get_corporation_corporation_id_mining_observers_observer_id(
            corporation_id=self.owner.corporation.corporation_id,
            observer_id=self.id,
            token=self.owner.fetch_token().valid_access_token(),
        ).results()
        # preload all missing ore types
        EveOreType.objects.bulk_get_or_create_esi(
            ids={record["type_id"] for record in records}
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
