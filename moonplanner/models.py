from typing import Optional

from django.core.exceptions import ObjectDoesNotExist
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from allianceauth.eveonline.models import EveCharacter, EveCorporationInfo
from esi.models import Token
from eveuniverse.models import EveMoon, EveType

from . import constants
from .app_settings import MOONPLANNER_REPROCESSING_YIELD, MOONPLANNER_VOLUME_PER_MONTH


def calc_refined_value(
    eve_type: EveType, volume: float, reprocessing_yield: float
) -> Optional[float]:
    volume_per_unit = eve_type.volume
    units = volume / volume_per_unit
    r_units = units / 100
    value = None
    for type_material in eve_type.materials.all():
        try:
            price = type_material.eve_type.market_price.average_price
        except (ObjectDoesNotExist, AttributeError):
            continue
        if price:
            if value is None:
                value = 0
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

    def __str__(self):
        return self.eve_moon.name

    def update_income_estimate(self, total_volume=None, reprocessing_yield=None):
        """Update income for this moon."""
        income = self.calc_income_estimate(
            total_volume=total_volume, reprocessing_yield=reprocessing_yield
        )
        self.income = income
        self.save()

    def calc_income_estimate(
        self, total_volume=None, reprocessing_yield=None, moon_product=None
    ):
        """Return calculated income estimate for given parameters.

        Args:
            total_volume: total excepted ore volume for this moon
            reprocessing_yield: expected average yield for ore reprocessing
            moon_product(optional): restrict estimation to given moon product

        Returns:
            income estimate for moon or None if prices or products are missing
        """
        if not total_volume:
            total_volume = MOONPLANNER_VOLUME_PER_MONTH
        if not reprocessing_yield:
            reprocessing_yield = MOONPLANNER_REPROCESSING_YIELD
        income = None
        if moon_product is None:
            moon_products = self.products.select_related("eve_type")
            if moon_products.count() == 0:
                return None
        else:
            moon_products = [moon_product]

        for product in moon_products:
            if product.eve_type.volume:
                income = calc_refined_value(
                    eve_type=product.eve_type,
                    volume=total_volume * product.amount,
                    reprocessing_yield=reprocessing_yield,
                )
                # volume_per_unit = product.eve_type.volume
                # volume = total_volume * product.amount
                # units = volume / volume_per_unit
                # r_units = units / 100
                # for type_material in product.eve_type.materials.all():
                #     price = type_material.eve_type.market_price.average_price
                #     if price:
                #         income += (
                #             price
                #             * type_material.quantity
                #             * r_units
                #             * reprocessing_yield

        return income

    def is_owned(self):
        return hasattr(self, "refinery")


class MoonProduct(models.Model):
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
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "{} - {}".format(self.eve_type.type_name, self.amount)

    # class Meta:
    #     unique_together = (("eve_moon", "eve_type"),)
    #     indexes = [
    #         models.Index(fields=["eve_moon"]),
    #     ]


class MiningCorporation(models.Model):
    corporation = models.OneToOneField(
        EveCorporationInfo,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="mining_corporations",
    )
    character = models.OneToOneField(
        EveCharacter, on_delete=models.DO_NOTHING, default=None, null=True
    )

    def __str__(self):
        return self.corporation.corporation_name

    @classmethod
    def get_esi_scopes(cls):
        return [
            "esi-industry.read_corporation_mining.v1",
            "esi-universe.read_structures.v1",
            "esi-characters.read_notifications.v1",
            "esi-corporations.read_structures.v1",
        ]

    def fetch_token(self):
        """Fetch token for this mining corp and return it..."""
        return (
            Token.objects.filter(character_id=self.character.character_id)
            .require_scopes(self.get_esi_scopes())
            .require_valid()
            .first()
        )


class Refinery(models.Model):

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

    def calc_value_estimate(self, reprocessing_yield=None):
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
        # volume_per_unit = self.eve_type.volume
        # units = self.volume / volume_per_unit
        # r_units = units / 100
        # value = 0
        # try:
        #     for type_material in self.eve_type.materials.all():
        #         price = type_material.eve_type.market_price.average_price
        #         if price:
        #             value += (
        #                 price * type_material.quantity * r_units * reprocessing_yield
        #             )
        # except models.ObjectDoesNotExist:
        #     value = None
        # else:
        #     return value
