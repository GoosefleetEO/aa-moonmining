from django.db import models
from allianceauth.eveonline.models import EveCorporationInfo, EveCharacter
from evesde.models import EveSolarSystem, EveItem, EveType, EveTypeMaterial


class Moon(models.Model):
    moon = models.OneToOneField(
        EveItem,         
        on_delete=models.CASCADE,
        primary_key=True
    )
    system = models.ForeignKey(
        EveSolarSystem,         
        on_delete=models.DO_NOTHING,        
        null=True, 
        default=None
    )
    income = models.FloatField(
        null=True, 
        default=None
    )    
    
    def __str__(self):
        return str(self.moon.evename)

    def calc_income_estimate(
        self, 
        total_volume, 
        reprocessing_yield, 
        moon_product = None):
        """returns newly calculated income estimate for a given volume in ISK
        
        Args:
            total_volume: total excepted ore volume for this moon
            reprocessing_yield: expected average yield for ore reprocessing
            moon_product(optional): restrict estimation to given moon product
        
        """
        income = 0        
        if moon_product is None:
            moon_products = self.moonproduct_set.select_related('type')
        else:
            moon_products = [moon_product]
        for product in moon_products:
            volume_per_unit = product.type.volume
            volume = total_volume * product.amount
            units = volume / volume_per_unit      
            r_units = units / 100
            for t in EveTypeMaterial.objects.filter(type=product.type).select_related('material_type__marketprice'):
                income += (t.material_type.marketprice.average_price
                    * t.quantity
                    * r_units
                    * reprocessing_yield)

        return income

    class Meta:
        permissions = (
            ('view_moonstuff', 'Can access the moonstuff module.'),
            ('view_all_moons', 'Can see all moons'),
        )


class MoonProduct(models.Model):
    moon = models.ForeignKey(
        Moon,        
        on_delete=models.CASCADE
    )
    type = models.ForeignKey(
        EveType,         
        on_delete=models.DO_NOTHING,
        null=True, 
        default=None
    )
    amount = models.FloatField()

    def __str__(self):
        return "{} - {}".format(self.type.type_name, self.amount)

    class Meta:
        unique_together = (('moon', 'type'),)
        indexes = [
            models.Index(fields=['moon']),
        ]


class Refinery(models.Model):
    name = models.CharField(max_length=150)
    structure_id = models.BigIntegerField()
    type = models.ForeignKey(EveType, on_delete=models.CASCADE)
    location = models.ForeignKey(Moon, on_delete=models.CASCADE)
    owner = models.ForeignKey(EveCorporationInfo, on_delete=models.CASCADE)

    def __str__(self):
        return self.name


class ExtractEvent(models.Model):
    start_time = models.DateTimeField()
    arrival_time = models.DateTimeField()
    decay_time = models.DateTimeField()
    structure = models.ForeignKey(Refinery, on_delete=models.CASCADE)
    moon = models.ForeignKey(Moon, on_delete=models.CASCADE)
    corp = models.ForeignKey(EveCorporationInfo, on_delete=models.CASCADE)

    class Meta:
        unique_together = (('arrival_time', 'moon'),)

    def __str__(self):
        return "{} - {}".format(self.moon.name, self.arrival_time)


class MoonDataCharacter(models.Model):
    character = models.OneToOneField(EveCharacter, on_delete=models.CASCADE)
    latest_notification = models.BigIntegerField(null=True, default=0)


class MarketPrice(models.Model):
    type = models.OneToOneField(
        EveType, 
        on_delete=models.CASCADE,
        primary_key=True
    )
    average_price = models.FloatField(null=True, default=None)
    adjusted_price = models.FloatField(null=True, default=None)
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):        
        if not self.average_price is None:
            return "{} {:,.2f}".format(self.type.type_name, self.average_price)
        else:
            return "{} {}".format(self.type.type_name, self.average_price)