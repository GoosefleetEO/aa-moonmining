from eveuniverse.models import EveMoon, EveType

from ..models import Moon, MoonProduct


def create_moons() -> list:
    Moon.objects.all().delete()
    moons = list()
    moon = Moon.objects.create(eve_moon=EveMoon.objects.get(id=40161708))
    MoonProduct.objects.create(
        moon=moon, eve_type=EveType.objects.get(id=45506), amount=0.19
    )
    MoonProduct.objects.create(
        moon=moon, eve_type=EveType.objects.get(id=46676), amount=0.23
    )
    MoonProduct.objects.create(
        moon=moon, eve_type=EveType.objects.get(id=46678), amount=0.25
    )
    MoonProduct.objects.create(
        moon=moon, eve_type=EveType.objects.get(id=46689), amount=0.33
    )
    moons.append(moon)
    return moons
