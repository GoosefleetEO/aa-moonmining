import datetime as dt

from django.utils.timezone import now

from allianceauth.eveonline.models import EveCorporationInfo
from eveuniverse.models import EveMoon, EveType

from ..app_settings import MOONPLANNER_VOLUME_PER_MONTH
from ..models import (
    Extraction,
    ExtractionProduct,
    MiningCorporation,
    Moon,
    MoonProduct,
    Refinery,
)


def create_moon() -> EveMoon:
    Moon.objects.filter(pk=40161708).delete()
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
    return moon


def add_refinery(moon: Moon, corporation: MiningCorporation = None) -> Refinery:
    if not corporation:
        corporation, _ = MiningCorporation.objects.get_or_create(
            corporation=EveCorporationInfo.objects.get(corporation_id=2001)
        )
    refinery = Refinery.objects.create(
        id=moon.eve_moon_id,
        moon=moon,
        corporation=corporation,
        eve_type=EveType.objects.get(id=35835),
    )
    extraction = Extraction.objects.create(
        refinery=refinery,
        ready_time=now() + dt.timedelta(days=3),
        auto_time=now() + dt.timedelta(days=3, hours=12),
    )
    for product in moon.products.all():
        ExtractionProduct.objects.create(
            extraction=extraction,
            eve_type=product.eve_type,
            volume=MOONPLANNER_VOLUME_PER_MONTH * product.amount,
        )
    return refinery
