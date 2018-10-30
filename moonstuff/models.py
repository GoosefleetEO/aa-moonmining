from django.db import models


# Create your models here.
class Resource(models.Model):
    ore = models.TextField(max_length=75)
    ore_id = models.IntegerField()
    amount = models.DecimalField(max_digits=11, decimal_places=10)


class Moon(models.Model):
    system_id = models.TextField(max_length=8)
    moon_id = models.IntegerField()
    resources = models.ManyToManyField(Resource)


def get_fallback_moon():
    return Moon.objects.get_or_create(system_id=30000142, moon_id=40009087)


class Refinery(models.Model):
    name = models.TextField(max_length=150)
    structure_id = models.IntegerField()
    size = models.BooleanField()
    location = models.ForeignKey(Moon, on_delete=models.SET(get_fallback_moon))

    @property
    def size_to_string(self):
        if self.size is True:
            return "Large"
        else:
            return "Medium"


class ExtractEvent(models.Model):
    start_time = models.DateTimeField()
    arrival_time = models.DateTimeField()
    decay_time = models.DateTimeField()
    structure = models.ForeignKey(Refinery, on_delete=models.CASCADE)
    moon = models.ForeignKey(Moon, on_delete=models.CASCADE)
