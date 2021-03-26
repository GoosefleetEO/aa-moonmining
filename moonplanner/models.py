from typing import Iterable

import yaml

from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from esi.models import Token
from eveuniverse.models import EveEntity, EveMoon, EveSolarSystem, EveType

from allianceauth.authentication.models import CharacterOwnership
from allianceauth.eveonline.models import EveCorporationInfo
from allianceauth.services.hooks import get_extension_logger
from app_utils.datetime import ldap_time_2_datetime
from app_utils.logging import LoggerAddTag

from . import __title__, constants
from .app_settings import MOONPLANNER_REPROCESSING_YIELD, MOONPLANNER_VOLUME_PER_MONTH
from .managers import EveOreTypeManger, MoonManager
from .providers import esi

logger = LoggerAddTag(get_extension_logger(__name__), __title__)
# MAX_DISTANCE_TO_MOON_METERS = 3000000


class EveOreType(EveType):
    """Subset of EveType for all ore types.

    Ensures Section.TYPE_MATERIALS is always enabled and allows adding methods to types.
    """

    URL_PROFILE_TYPE = "https://www.kalkoken.org/apps/eveitems/"

    class Meta:
        proxy = True

    objects = EveOreTypeManger()

    @property
    def profile_url(self) -> str:
        return f"{self.URL_PROFILE_TYPE}?typeId={self.id}"

    def calc_refined_value(
        self, volume: float, reprocessing_yield: float = None
    ) -> float:
        """Calculate the refined total value and return it."""
        if not reprocessing_yield:
            reprocessing_yield = MOONPLANNER_REPROCESSING_YIELD
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

    @classmethod
    def _enabled_sections_union(cls, enabled_sections: Iterable[str]) -> set:
        """Return enabled sections with TYPE_MATERIALS always enabled."""
        enabled_sections = super()._enabled_sections_union(
            enabled_sections=enabled_sections
        )
        enabled_sections.add(cls.Section.TYPE_MATERIALS)
        return enabled_sections


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
        EveMoon, on_delete=models.CASCADE, primary_key=True, related_name="known_moon"
    )
    value = models.FloatField(
        null=True, default=None, validators=[MinValueValidator(0.0)]
    )
    products_updated_at = models.DateTimeField(null=True, default=None)
    products_updated_by = models.ForeignKey(
        User, on_delete=models.SET_DEFAULT, null=True, default=None
    )

    objects = MoonManager()

    def __str__(self):
        return self.eve_moon.name

    def update_value(self) -> float:
        """Update value estimate with given parameters."""
        value = sum(
            [
                product.calc_value(total_volume=MOONPLANNER_VOLUME_PER_MONTH)
                for product in self.products.select_related("ore_type")
            ]
        )
        self.value = value if value else None
        self.save()

    def is_owned(self):
        return hasattr(self, "refinery")


class MoonProduct(models.Model):
    """A product of a moon, i.e. a specifc ore."""

    moon = models.ForeignKey(Moon, on_delete=models.CASCADE, related_name="products")
    ore_type = models.ForeignKey(EveOreType, on_delete=models.CASCADE, related_name="+")
    amount = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )

    def __str__(self):
        return f"{self.ore_type.name} - {self.amount}"

    # class Meta:
    #     unique_together = (("eve_moon", "eve_type"),)
    #     indexes = [
    #         models.Index(fields=["eve_moon"]),
    #     ]

    def calc_value(self, total_volume=None, reprocessing_yield=None) -> float:
        """Return calculated value estimate for given parameters.

        Args:
            total_volume: total excepted ore volume for this moon
            reprocessing_yield: expected average yield for ore reprocessing

        Returns:
            value estimate for moon or None if prices or products are missing
        """
        if not total_volume:
            total_volume = MOONPLANNER_VOLUME_PER_MONTH
        return self.ore_type.calc_refined_value(
            volume=total_volume * self.amount, reprocessing_yield=reprocessing_yield
        )


class MiningCorporation(models.Model):
    """An EVE Online corporation running mining operations."""

    eve_corporation = models.OneToOneField(
        EveCorporationInfo,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="mining_corporation",
    )
    character_ownership = models.ForeignKey(
        CharacterOwnership,
        on_delete=models.SET_DEFAULT,
        default=None,
        null=True,
        related_name="+",
        help_text="character used to sync this corporation from ESI",
    )
    last_update_at = models.DateTimeField(null=True, default=None)

    def __str__(self):
        alliance_ticker_str = (
            f" [{self.eve_corporation.alliance.alliance_ticker}]"
            if self.eve_corporation.alliance
            else ""
        )
        return f"{self.eve_corporation}{alliance_ticker_str}"

    def fetch_token(self):
        """Fetch token for this mining corp and return it..."""
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
        token = self.fetch_token()
        refineries = self._fetch_refineries_from_esi(token)
        for structure_id, _ in refineries.items():
            self._update_or_create_refinery_from_esi(structure_id, token)

        # remove refineries that no longer exist
        self.refineries.exclude(id__in=refineries).delete()

    def _fetch_refineries_from_esi(self, token: Token) -> dict:
        logger.info("%s: Fetching refineries from ESI...", self)
        structures = esi.client.Corporation.get_corporations_corporation_id_structures(
            corporation_id=self.eve_corporation.corporation_id,
            token=token.valid_access_token(),
        ).result()
        refineries = dict()
        for structure_info in structures:
            eve_type, _ = EveType.objects.get_or_create_esi(
                id=structure_info["type_id"]
            )
            structure_info["_eve_type"] = eve_type
            if eve_type.eve_group_id == constants.EVE_GROUP_ID_REFINERY:
                refineries[structure_info["structure_id"]] = structure_info
        return refineries

    def _update_or_create_refinery_from_esi(self, structure_id: int, token: Token):
        logger.info("%s: Fetching details for refinery #%d", self, structure_id)
        try:
            structure_info = esi.client.Universe.get_universe_structures_structure_id(
                structure_id=structure_id, token=token.valid_access_token()
            ).result()
        except OSError:
            logger.exception("%s: Failed to fetch refinery #%d", self, structure_id)
            return
        refinery, _ = Refinery.objects.update_or_create(
            id=structure_id,
            defaults={
                "name": structure_info["name"],
                "eve_type": EveType.objects.get(id=structure_info["type_id"]),
                "corporation": self,
            },
        )
        if not refinery.moon:
            refinery.update_moon_from_structure_info(structure_info)

    def update_extractions_from_esi(self):
        """Update all extractions from ESI."""
        notifications = self._fetch_moon_notifications_from_esi()
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
        for notification in sorted(notifications, key=lambda k: k["timestamp"]):
            parsed_text = yaml.safe_load(notification["text"])
            structure_id = parsed_text["structureID"]
            try:
                refinery = Refinery.objects.get(id=structure_id)
            except Refinery.DoesNotExist:
                refinery = None
            # update the refinery's moon from notification
            # in case it was not found by nearest_celestial
            if refinery and not refinery.moon:
                refinery.update_moon_from_eve_id(parsed_text["moonID"])

            if notification["type"] == "MoonminingExtractionStarted":
                if not refinery:
                    continue  # we ignore notifications for unknown refineries
                started_by_id = parsed_text.get("startedBy")
                if started_by_id:
                    try:
                        started_by, _ = EveEntity.objects.get_or_create_esi(
                            id=started_by_id
                        )
                    except OSError:
                        started_by = None
                else:
                    started_by = None
                extraction, _ = Extraction.objects.get_or_create(
                    refinery=refinery,
                    ready_time=ldap_time_2_datetime(parsed_text["readyTime"]),
                    defaults={
                        "auto_time": ldap_time_2_datetime(parsed_text["autoTime"]),
                        "started_by": started_by,
                    },
                )
                last_extraction_started[structure_id] = extraction
                ore_volume_by_type = parsed_text["oreVolumeByType"].items()
                for ore_type_id, ore_volume in ore_volume_by_type:
                    ore_type, _ = EveOreType.objects.get_or_create_esi(id=ore_type_id)
                    ExtractionProduct.objects.get_or_create(
                        extraction=extraction,
                        ore_type=ore_type,
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

    def _fetch_moon_notifications_from_esi(self):
        logger.info("%s: Fetching moon notifications from ESI...", self)
        token = self.fetch_token()
        all_notifications = (
            esi.client.Character.get_characters_character_id_notifications(
                character_id=self.character_ownership.character.character_id,
                token=token.valid_access_token(),
            ).result()
        )
        return [
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

    @classmethod
    def esi_scopes(cls):
        """Return list of all required esi scopes."""
        return [
            "esi-industry.read_corporation_mining.v1",
            "esi-universe.read_structures.v1",
            "esi-characters.read_notifications.v1",
            "esi-corporations.read_structures.v1",
        ]


class Refinery(models.Model):
    """An Eve Online refinery structure."""

    id = models.BigIntegerField(primary_key=True)
    name = models.CharField(max_length=150, db_index=True)
    moon = models.OneToOneField(
        Moon,
        on_delete=models.SET_DEFAULT,
        default=None,
        null=True,
        related_name="refinery",
    )
    corporation = models.ForeignKey(
        MiningCorporation, on_delete=models.CASCADE, related_name="refineries"
    )
    eve_type = models.ForeignKey(EveType, on_delete=models.CASCADE, related_name="+")

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


class Extraction(models.Model):
    """A mining extraction."""

    refinery = models.ForeignKey(
        Refinery, on_delete=models.CASCADE, related_name="extractions"
    )
    ready_time = models.DateTimeField(db_index=True)
    auto_time = models.DateTimeField()
    value = models.FloatField(
        null=True, default=None, validators=[MinValueValidator(0.0)]
    )
    started_by = models.ForeignKey(
        EveEntity,
        on_delete=models.SET_DEFAULT,
        default=None,
        null=True,
        related_name="+",
    )

    # class Meta:
    #     unique_together = (("ready_time", "refinery"),)

    def __str__(self) -> str:
        return f"{self.refinery} - {self.ready_time}"

    def update_value(self) -> float:
        """Update value estimate with given parameters.

        Args:
            reprocessing_yield: expected average yield for ore reprocessing
        """
        value = sum(
            [
                product.calc_value()
                for product in self.products.select_related("ore_type")
            ]
        )
        self.value = value
        self.save()


class ExtractionProduct(models.Model):
    """A product within a mining extraction."""

    extraction = models.ForeignKey(
        Extraction, on_delete=models.CASCADE, related_name="products"
    )
    ore_type = models.ForeignKey(EveOreType, on_delete=models.CASCADE, related_name="+")
    volume = models.FloatField(validators=[MinValueValidator(0.0)])

    # class Meta:
    #     unique_together = (("extraction", "ore_type"),)

    def __str__(self) -> str:
        return f"{self.extraction} - {self.ore_type}"

    def calc_value(self, reprocessing_yield=None) -> float:
        """returns calculated value estimate in ISK

        Args:
            reprocessing_yield: expected average yield for ore reprocessing
        Returns:
            value estimate or None if prices are missing

        """
        return self.ore_type.calc_refined_value(
            volume=self.volume, reprocessing_yield=reprocessing_yield
        )
