from django.db import models
from django.db.models import Q

from allianceauth.eveonline.models import EveCharacter, EveCorporationInfo
from eveuniverse.models import EveMoon, EveType, EveTypeMaterial


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


class MoonIncome(models.Model):
    TYPE_MOON_ID = 14

    eve_moon = models.OneToOneField(
        EveMoon, on_delete=models.CASCADE, primary_key=True, related_name="income"
    )
    income = models.FloatField(null=True, default=None)

    def __str__(self):
        return self.eve_moon.name

    def calc_income_estimate(self, total_volume, reprocessing_yield, moon_product=None):
        """returns newly calculated income estimate for a given volume in ISK

        Args:
            total_volume: total excepted ore volume for this moon
            reprocessing_yield: expected average yield for ore reprocessing
            moon_product(optional): restrict estimation to given moon product

        Returns:
            income estimate for moon or None if prices or products are missing

        """
        income = 0
        if moon_product is None:
            moon_products = self.moonproduct_set.select_related("eve_type")
            if moon_products.count() == 0:
                return None
        else:
            moon_products = [moon_product]

        try:
            for product in moon_products:
                if product.eve_type.volume:
                    volume_per_unit = product.eve_type.volume
                    volume = total_volume * product.amount
                    units = volume / volume_per_unit
                    r_units = units / 100
                    types_qs = EveTypeMaterial.objects.filter(
                        type=product.eve_type
                    ).select_related("material_type__marketprice")
                    for t in types_qs:
                        income += (
                            t.material_type.marketprice.average_price
                            * t.quantity
                            * r_units
                            * reprocessing_yield
                        )
        except models.ObjectDoesNotExist:
            income = None

        return income

    def is_owned(self):
        return hasattr(self, "refinery")


class MoonProduct(models.Model):
    eve_moon = models.ForeignKey(
        EveMoon, on_delete=models.CASCADE, related_name="products"
    )
    eve_type = models.ForeignKey(
        EveType,
        on_delete=models.DO_NOTHING,
        null=True,
        default=None,
        limit_choices_to=Q(group__category_id=25),
        related_name="+",
    )
    amount = models.FloatField()

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


class Refinery(models.Model):
    TYPE_REFINERY_ID = 1406

    structure_id = models.BigIntegerField(primary_key=True)
    eve_moon = models.OneToOneField(
        EveMoon,
        on_delete=models.SET_DEFAULT,
        default=None,
        null=True,
        related_name="refinery",
    )
    name = models.CharField(max_length=150)
    corporation = models.ForeignKey(MiningCorporation, on_delete=models.CASCADE)
    eve_type = models.ForeignKey(
        EveType,
        on_delete=models.CASCADE,
        limit_choices_to={"id": TYPE_REFINERY_ID},
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
        on_delete=models.DO_NOTHING,
        null=True,
        default=None,
        limit_choices_to=Q(eve_group__eve_category_id=25),
    )
    volume = models.FloatField()

    # class Meta:
    #     unique_together = (("extraction", "eve_type"),)

    def __str__(self):
        return "{} - {}".format(self.extraction, self.eve_type)

    def calc_value_estimate(self, reprocessing_yield):
        """returns calculated value estimate in ISK

        Args:
            reprocessing_yield: expected average yield for ore reprocessing
        Returns:
            value estimate or None if prices are missing

        """
        volume_per_unit = self.eve_type.volume
        units = self.volume / volume_per_unit
        r_units = units / 100
        value = 0
        try:
            types_qs = EveTypeMaterial.objects.filter(type=self.eve_type)
            for t in types_qs:
                value += (
                    t.material_type.marketprice.average_price
                    * t.quantity
                    * r_units
                    * reprocessing_yield
                )
        except models.ObjectDoesNotExist:
            value = None
        else:
            return value
