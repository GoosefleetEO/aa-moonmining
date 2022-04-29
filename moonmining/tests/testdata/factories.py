import datetime as dt
import random

import factory
import factory.fuzzy

from django.utils.timezone import now
from eveuniverse.models import EveEntity, EveMoon, EveType

from allianceauth.eveonline.models import EveCorporationInfo
from app_utils.testing import create_user_from_evecharacter

from ...app_settings import MOONMINING_VOLUME_PER_DAY
from ...constants import EveTypeId
from ...core import CalculatedExtraction
from ...models import (
    EveOreType,
    Extraction,
    ExtractionProduct,
    MiningLedgerRecord,
    Moon,
    MoonProduct,
    Owner,
    Refinery,
)


def random_percentages(num_parts: int) -> list:
    percentages = []
    total = 0
    for _ in range(num_parts - 1):
        part = random.randint(0, 100 - total)
        percentages.append(part)
        total += part
    percentages.append(100 - total)
    return percentages


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

    @factory.post_generation
    def create_products(obj, create, extracted, **kwargs):
        """Set this param to False to disable."""
        if not create or extracted is False:
            return
        for product in obj.refinery.moon.products.all():
            ExtractionProductFactory(
                extraction=obj,
                ore_type=product.ore_type,
                volume=MOONMINING_VOLUME_PER_DAY
                * obj.duration_in_days
                * product.amount,
            )
        obj.update_calculated_properties()


class ExtractionProductFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ExtractionProduct


class MiningLedgerRecordFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = MiningLedgerRecord

    day = factory.LazyFunction(lambda: now().date())
    character = factory.LazyFunction(lambda: EveEntity.objects.get(id=1001))
    corporation = factory.LazyFunction(lambda: EveEntity.objects.get(id=2001))
    ore_type = factory.LazyFunction(
        lambda: EveOreType.objects.get(id=EveTypeId.CINNABAR)
    )
    quantity = factory.fuzzy.FuzzyInteger(10000)


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
