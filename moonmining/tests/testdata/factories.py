import datetime as dt
import random

from django.utils.timezone import now
from eveuniverse.models import EveMoon

from allianceauth.eveonline.models import EveCorporationInfo

from ...app_settings import MOONMINING_VOLUME_PER_DAY
from ...constants import EveTypeId
from ...models import (
    EveOreType,
    Extraction,
    ExtractionProduct,
    Moon,
    MoonProduct,
    Owner,
    Refinery,
)


def random_percentages(parts) -> list:
    percentages = []
    total = 0
    for _ in range(parts - 1):
        part = random.randint(0, 100 - total)
        percentages.append(part)
        total += part
    percentages.append(100 - total)
    return percentages


def create_moon_product(moon: Moon, **kwargs) -> MoonProduct:
    params = {"moon": moon}
    params.update(kwargs)
    return MoonProduct.objects.create(**params)


def create_moon(**kwargs) -> Moon:
    """Created new Moon object for a random moon."""
    used_ids = list(Moon.objects.values_list("eve_moon_id", flat=True))
    unused_ids = list(
        EveMoon.objects.exclude(id__in=used_ids).values_list("id", flat=True)
    )
    if not unused_ids:
        raise RuntimeError("No unused moon left")
    params = {"eve_moon_id": random.choice(unused_ids), "products_updated_at": now()}
    params.update(kwargs)
    moon = Moon.objects.create(**params)
    ore_type_ids = [EveTypeId.CHROMITE, EveTypeId.EUXENITE, EveTypeId.XENOTIME]
    percentages = random_percentages(3)
    for ore_type_id in ore_type_ids:
        ore_type, _ = EveOreType.objects.get_or_create_esi(id=ore_type_id)
        create_moon_product(
            moon=moon, ore_type=ore_type, amount=percentages.pop() / 100
        )
    moon.update_calculated_properties()
    return moon


def create_owner(**kwargs):
    """Create owner from random corporation."""
    params = {}
    if "corporation_id" not in kwargs and "corporation" not in kwargs:
        used_ids = list(Owner.objects.values_list("corporation_id", flat=True))
        unused_ids = list(
            EveCorporationInfo.objects.exclude(corporation_id__in=used_ids).values_list(
                "corporation_id", flat=True
            )
        )
        if not unused_ids:
            raise RuntimeError("No unused corporations left")
    params.update(kwargs)
    return Owner.objects.create(**kwargs)


def create_refinery(**kwargs):
    params = {}
    if "moon" not in kwargs and "moon_id" not in kwargs:
        params["moon"] = create_moon()
    if "owner" not in kwargs and "owner_id" not in kwargs:
        params["owner"] = create_owner()
    if "eve_type" not in kwargs and "eve_type_id" not in kwargs:
        params["eve_type_id"] = EveTypeId.ATHANOR
    params.update(kwargs)
    if "moon" in params:
        params["id"] = params["moon"].id
    elif "moon_id" in params:
        params["id"] = params["moon_id"]
    return Refinery.objects.create(**params)


def create_extraction_product(extraction: Extraction, **kwargs):
    params = {"extraction": extraction}
    params.update(kwargs)
    return ExtractionProduct.objects.create(**params)


def create_extraction(**kwargs):
    params = {
        "chunk_arrival_at": now() + dt.timedelta(days=3),
        "auto_fracture_at": now() + dt.timedelta(days=3, hours=12),
        "started_at": now() - dt.timedelta(days=3),
        "status": Extraction.Status.STARTED,
    }
    if "refinery" in kwargs:
        refinery = kwargs["refinery"]
    elif "refinery_id" in kwargs:
        refinery = Refinery.objects.get(id=kwargs["refinery_id"])
    else:
        params["refinery"] = refinery = create_refinery()
    params.update(kwargs)
    if "refinery" in params:
        refinery = params["refinery"]
    extraction = Extraction.objects.create(**params)
    for product in refinery.moon.products.all():
        create_extraction_product(
            extraction=extraction,
            ore_type=product.ore_type,
            volume=MOONMINING_VOLUME_PER_DAY
            * extraction.duration_in_days
            * product.amount,
        )
    return extraction
