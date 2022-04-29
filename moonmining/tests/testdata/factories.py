import datetime as dt
import random

import factory

from django.utils.timezone import now
from eveuniverse.models import EveMoon, EveType

from allianceauth.eveonline.models import EveCorporationInfo
from app_utils.testing import create_user_from_evecharacter

# from ...app_settings import MOONMINING_VOLUME_PER_DAY
from ...constants import EveTypeId
from ...core import CalculatedExtraction
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


# def create_moon_product(moon: Moon, **kwargs) -> MoonProduct:
#     params = {"moon": moon}
#     params.update(kwargs)
#     return MoonProduct.objects.create(**params)


# def create_moon(**kwargs) -> Moon:
#     """Created new Moon object for a random moon."""
#     used_ids = list(Moon.objects.values_list("eve_moon_id", flat=True))
#     unused_ids = list(
#         EveMoon.objects.exclude(id__in=used_ids).values_list("id", flat=True)
#     )
#     if not unused_ids:
#         raise RuntimeError("No unused moon left")
#     params = {"eve_moon_id": random.choice(unused_ids), "products_updated_at": now()}
#     params.update(kwargs)
#     moon = Moon.objects.create(**params)
#     ore_type_ids = [EveTypeId.CHROMITE, EveTypeId.EUXENITE, EveTypeId.XENOTIME]
#     percentages = random_percentages(3)
#     for ore_type_id in ore_type_ids:
#         ore_type, _ = EveOreType.objects.get_or_create_esi(id=ore_type_id)
#         create_moon_product(
#             moon=moon, ore_type=ore_type, amount=percentages.pop() / 100
#         )
#     moon.update_calculated_properties()
#     return moon


# def create_owner(**kwargs):
#     """Create owner from random corporation."""
#     params = {}
#     if "corporation_id" not in kwargs and "corporation" not in kwargs:
#         used_ids = list(Owner.objects.values_list("corporation_id", flat=True))
#         unused_ids = list(
#             EveCorporationInfo.objects.exclude(corporation_id__in=used_ids).values_list(
#                 "corporation_id", flat=True
#             )
#         )
#         if not unused_ids:
#             raise RuntimeError("No unused corporations left")
#     params.update(kwargs)
#     return Owner.objects.create(**kwargs)


# def create_refinery(**kwargs):
#     params = {}
#     if "moon" not in kwargs and "moon_id" not in kwargs:
#         params["moon"] = create_moon()
#     if "owner" not in kwargs and "owner_id" not in kwargs:
#         params["owner"] = create_owner()
#     if "eve_type" not in kwargs and "eve_type_id" not in kwargs:
#         params["eve_type_id"] = EveTypeId.ATHANOR
#     params.update(kwargs)
#     if "moon" in params:
#         params["id"] = params["moon"].id
#     elif "moon_id" in params:
#         params["id"] = params["moon_id"]
#     return Refinery.objects.create(**params)


# def create_extraction_product(extraction: Extraction, **kwargs):
#     params = {"extraction": extraction}
#     params.update(kwargs)
#     return ExtractionProduct.objects.create(**params)


# def create_extraction(**kwargs):
#     params = {
#         "chunk_arrival_at": now() + dt.timedelta(days=3),
#         "auto_fracture_at": now() + dt.timedelta(days=3, hours=12),
#         "started_at": now() - dt.timedelta(days=3),
#         "status": Extraction.Status.STARTED,
#     }
#     if "refinery" in kwargs:
#         refinery = kwargs["refinery"]
#     elif "refinery_id" in kwargs:
#         refinery = Refinery.objects.get(id=kwargs["refinery_id"])
#     else:
#         params["refinery"] = refinery = create_refinery()
#     params.update(kwargs)
#     if "refinery" in params:
#         refinery = params["refinery"]
#     extraction = Extraction.objects.create(**params)
#     for product in refinery.moon.products.all():
#         create_extraction_product(
#             extraction=extraction,
#             ore_type=product.ore_type,
#             volume=MOONMINING_VOLUME_PER_DAY
#             * extraction.duration_in_days
#             * product.amount,
#         )
#     return extraction


class CalculatedExtractionFactory(factory.Factory):
    class Meta:
        model = CalculatedExtraction

    refinery_id = factory.Sequence(lambda n: n + 1)
    status = CalculatedExtraction.Status.STARTED
    started_at = factory.LazyFunction(now)
    chunk_arrival_at = factory.LazyAttribute(
        lambda obj: obj.started_at + dt.timedelta(days=20)
    )


class ExtractionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Extraction

    started_at = factory.LazyFunction(now)
    chunk_arrival_at = factory.LazyAttribute(
        lambda obj: obj.started_at + dt.timedelta(days=20)
    )
    auto_fracture_at = factory.LazyAttribute(
        lambda obj: obj.chunk_arrival_at + dt.timedelta(hours=3)
    )
    status = Extraction.Status.STARTED


class ExtractionProductFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ExtractionProduct


class MoonFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Moon
        exclude = ("create_products",)

    products_updated_at = factory.LazyFunction(now)

    @factory.lazy_attribute
    def eve_moon(self):
        return EveMoon.objects.exclude(
            id__in=list(Moon.objects.values_list("eve_moon_id", flat=True))
        ).first()

    @factory.post_generation
    def create_products(obj, create, extracted, **kwargs):
        """Set this param to False to disable."""
        if not create or extracted is False:
            return
        ore_type_ids = [EveTypeId.CHROMITE, EveTypeId.EUXENITE, EveTypeId.XENOTIME]
        percentages = random_percentages(3)
        for ore_type_id in ore_type_ids:
            ore_type, _ = EveOreType.objects.get_or_create_esi(id=ore_type_id)
            MoonProductFactory(
                moon=obj, ore_type=ore_type, amount=percentages.pop() / 100
            )
        obj.update_calculated_properties()


class MoonProductFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = MoonProduct


class OwnerFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Owner

    last_update_at = factory.LazyFunction(now)
    last_update_ok = True

    @factory.lazy_attribute
    def character_ownership(self):
        _, obj = create_user_from_evecharacter(
            1001,
            permissions=[
                "moonmining.basic_access",
                "moonmining.upload_moon_scan",
                "moonmining.extractions_access",
                "moonmining.add_refinery_owner",
            ],
            scopes=Owner.esi_scopes(),
        )
        return obj

    @factory.lazy_attribute
    def corporation(self):
        corporation_id = (
            self.character_ownership.character.corporation_id
            if self.character_ownership
            else 2001
        )
        return EveCorporationInfo.objects.get(corporation_id=corporation_id)


class RefineryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Refinery

    id = factory.Sequence(lambda n: n + 1900000000001)
    name = factory.Faker("city")
    moon = factory.SubFactory(MoonFactory)
    owner = factory.SubFactory(OwnerFactory)

    @factory.lazy_attribute
    def eve_type(self):
        return EveType.objects.get(id=EveTypeId.ATHANOR)


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "auth.User"
        django_get_or_create = ("username",)

    username = "Bruce_Wayne"
    first_name = "Bruce"
    last_name = "Wayne"
