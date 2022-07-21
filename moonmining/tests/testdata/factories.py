import datetime as dt
import random
from typing import List

import factory
import factory.fuzzy
import pytz

from django.utils.timezone import now
from eveuniverse.models import EveEntity, EveMoon, EveType

from allianceauth.eveonline.models import EveCorporationInfo
from app_utils.testdata_factories import (
    EveCharacterFactory,
    EveCorporationInfoFactory,
    UserMainFactory,
)
from app_utils.testing import create_user_from_evecharacter

from ...app_settings import MOONMINING_VOLUME_PER_DAY
from ...constants import EveTypeId
from ...core import CalculatedExtraction, CalculatedExtractionProduct
from ...models import (
    EveOreType,
    Extraction,
    ExtractionProduct,
    MiningLedgerRecord,
    Moon,
    MoonProduct,
    Notification,
    NotificationType,
    Owner,
    Refinery,
)

FUZZY_START_YEAR = 2008


def datetime_to_ldap(my_dt: dt.datetime) -> int:
    """datetime.datetime to ldap"""
    return (
        ((my_dt - dt.datetime(1970, 1, 1, tzinfo=pytz.utc)).total_seconds())
        + 11644473600
    ) * 10000000


# Auth


class DefaultOwnerUserMainFactory(UserMainFactory):
    main_character__scopes = Owner.esi_scopes()
    permissions__ = [
        "moonmining.basic_access",
        "moonmining.upload_moon_scan",
        "moonmining.extractions_access",
        "moonmining.add_refinery_owner",
    ]

    @factory.lazy_attribute
    def main_character__character(self):
        corporation = EveCorporationInfoFactory(
            corporation_id=2001, corporation_name="Wayne Technologies"
        )
        return EveCharacterFactory(
            character_id=1001, character_name="Bruce Wayne", corporation=corporation
        )


# eveuniverse


class EveEntityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = EveEntity
        django_get_or_create = ("id", "name")

    id = factory.Sequence(lambda n: 10_001 + n)


class EveEntityCharacterFactory(EveEntityFactory):
    name = factory.Faker("name")
    category = EveEntity.CATEGORY_CHARACTER


class EveEntityCorporationFactory(EveEntityFactory):
    name = factory.Faker("company")
    category = EveEntity.CATEGORY_CORPORATION


class EveEntityAllianceFactory(EveEntityFactory):
    name = factory.Faker("company")
    category = EveEntity.CATEGORY_ALLIANCE


# moonmining


def random_percentages(num_parts: int) -> List[float]:
    percentages = []
    total = 0
    for _ in range(num_parts - 1):
        part = random.randint(0, 100 - total)
        percentages.append(part)
        total += part
    percentages.append((100 - total) / 100)
    return percentages


def _generate_calculated_extraction_products(
    extraction: CalculatedExtraction,
) -> List[CalculatedExtractionProduct]:
    ore_type_ids = [EveTypeId.CHROMITE, EveTypeId.EUXENITE, EveTypeId.XENOTIME]
    percentages = random_percentages(3)
    duration = (
        (extraction.chunk_arrival_at - extraction.started_at).total_seconds()
        / 3600
        / 24
    )
    products = [
        CalculatedExtractionProductFactory(
            ore_type_id=ore_type_id,
            volume=percentages.pop() * MOONMINING_VOLUME_PER_DAY * duration,
        )
        for ore_type_id in ore_type_ids
    ]
    return products


class CalculatedExtractionProductFactory(factory.Factory):
    class Meta:
        model = CalculatedExtractionProduct


class CalculatedExtractionFactory(factory.Factory):
    class Meta:
        model = CalculatedExtraction

    auto_fracture_at = factory.LazyAttribute(
        lambda obj: obj.chunk_arrival_at + dt.timedelta(hours=3)
    )
    chunk_arrival_at = factory.LazyAttribute(
        lambda obj: obj.started_at + dt.timedelta(days=20)
    )
    refinery_id = factory.Sequence(lambda n: n + 1800000000001)
    status = CalculatedExtraction.Status.STARTED
    started_at = factory.fuzzy.FuzzyDateTime(
        dt.datetime(FUZZY_START_YEAR, 1, 1, tzinfo=pytz.utc), force_microsecond=0
    )

    @factory.lazy_attribute
    def started_by(self):
        character = EveEntityCharacterFactory(name="Bruce Wayne")
        return character.id

    @factory.lazy_attribute
    def products(self):
        return _generate_calculated_extraction_products(self)


class MiningLedgerRecordFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = MiningLedgerRecord

    day = factory.fuzzy.FuzzyDate((now() - dt.timedelta(days=120)).date())
    character = factory.SubFactory(EveEntityCharacterFactory)
    corporation = factory.SubFactory(EveEntityCorporationFactory)
    ore_type = factory.LazyFunction(lambda: EveOreType.objects.order_by("?").first())
    quantity = factory.fuzzy.FuzzyInteger(10000)


class MoonFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Moon
        exclude = ("create_products",)

    products_updated_at = factory.fuzzy.FuzzyDateTime(
        dt.datetime(FUZZY_START_YEAR, 1, 1, tzinfo=pytz.utc), force_microsecond=0
    )

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
            MoonProductFactory(moon=obj, ore_type=ore_type, amount=percentages.pop())
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


class ExtractionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Extraction

    started_at = factory.fuzzy.FuzzyDateTime(
        dt.datetime(FUZZY_START_YEAR, 1, 1, tzinfo=pytz.utc), force_microsecond=0
    )
    chunk_arrival_at = factory.LazyAttribute(
        lambda obj: obj.started_at + dt.timedelta(days=20)
    )
    auto_fracture_at = factory.LazyAttribute(
        lambda obj: obj.chunk_arrival_at + dt.timedelta(hours=3)
    )
    refinery = factory.SubFactory(RefineryFactory)
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


class NotificationFactory(factory.django.DjangoModelFactory):
    """Create notifications from Extraction objects."""

    class Meta:
        model = Notification

    class Params:
        extraction = factory.SubFactory(ExtractionFactory)

    notification_id = factory.Sequence(lambda n: 1_900_000_001 + n)
    owner = factory.LazyAttribute(lambda obj: obj.extraction.refinery.owner)
    created = factory.fuzzy.FuzzyDateTime(
        dt.datetime(FUZZY_START_YEAR, 1, 1, tzinfo=pytz.utc), force_microsecond=0
    )
    notif_type = factory.LazyAttribute(
        lambda obj: obj.extraction.status_enum.to_notification_type
    )
    last_updated = factory.LazyFunction(now)
    sender = factory.SubFactory(EveEntityCorporationFactory, name="DED")
    timestamp = factory.LazyAttribute(lambda obj: obj.extraction.started_at)

    @factory.lazy_attribute
    def details(self):
        def _details_link(character: EveEntity) -> str:
            return f'<a href="showinfo:1379//{character.id}">{character.name}</a>'

        def _to_ore_volume_by_type(extraction):
            return {
                str(obj.ore_type_id): obj.volume for obj in extraction.products.all()
            }

        refinery = self.extraction.refinery
        data = {
            "moonID": self.extraction.refinery.moon.eve_moon_id,
            "structureID": self.extraction.refinery_id,
            "solarSystemID": refinery.moon.solar_system().id,
            "structureLink": (
                f'<a href="showinfo:35835//{refinery.id}">{refinery.name}</a>'
            ),
            "structureName": refinery.name,
            "structureTypeID": refinery.eve_type_id,
        }
        if self.extraction.status == Extraction.Status.STARTED:
            started_by = (
                self.extraction.started_by
                if self.extraction.started_by
                else EveEntityCharacterFactory()
            )
            data.update(
                {
                    "autoTime": datetime_to_ldap(self.extraction.auto_fracture_at),
                    "readyTime": datetime_to_ldap(self.extraction.chunk_arrival_at),
                    "startedBy": started_by.id,
                    "startedByLink": _details_link(started_by),
                    "oreVolumeByType": _to_ore_volume_by_type(self.extraction),
                }
            )
        elif self.extraction.status == Extraction.Status.READY:
            data.update(
                {
                    "autoTime": datetime_to_ldap(self.extraction.auto_fracture_at),
                    "oreVolumeByType": _to_ore_volume_by_type(self.extraction),
                }
            )
        elif self.extraction.status == Extraction.Status.COMPLETED:
            data.update(
                {
                    "oreVolumeByType": _to_ore_volume_by_type(self.extraction),
                }
            )

        elif self.extraction.status == Extraction.Status.COMPLETED:
            fired_by = EveEntityCharacterFactory()
            data.update(
                {
                    "firedBy": fired_by.id,
                    "firedByLink": _details_link(fired_by),
                    "oreVolumeByType": _to_ore_volume_by_type(self.extraction),
                }
            )
        elif self.extraction.status == Extraction.Status.CANCELED:
            canceled_by = (
                self.extraction.canceled_by
                if self.extraction.canceled_by
                else EveEntityCharacterFactory()
            )
            data.update(
                {
                    "cancelledBy": canceled_by.id,
                    "cancelledByLink": _details_link(canceled_by),
                }
            )
        return data


class NotificationFactory2(factory.django.DjangoModelFactory):
    """Create notifications from CalculatedExtraction objects."""

    class Meta:
        model = Notification
        exclude = (
            "extraction",
            "moon_id",
            "solar_system_id",
            "structure_id",
            "structure_name",
            "structure_type_id",
        )

    class Params:
        create_products = False

    # regular
    notification_id = factory.Sequence(lambda n: 1_900_000_001 + n)
    owner = factory.SubFactory(OwnerFactory)
    created = factory.fuzzy.FuzzyDateTime(
        dt.datetime(FUZZY_START_YEAR, 1, 1, tzinfo=pytz.utc), force_microsecond=0
    )
    last_updated = factory.LazyFunction(now)
    sender = factory.SubFactory(EveEntityCorporationFactory, name="DED")
    timestamp = factory.LazyAttribute(lambda obj: obj.extraction.started_at)

    # excluded
    extraction = factory.SubFactory(CalculatedExtractionFactory)
    moon_id = 40161708  # Auga V - Moon 1
    solar_system_id = 30002542  # Auga V
    structure_name = factory.Faker("city")
    structure_type_id = EveTypeId.ATHANOR

    @factory.lazy_attribute
    def notif_type(self):
        status_map = {
            CalculatedExtraction.Status.STARTED: (
                NotificationType.MOONMINING_EXTRACTION_STARTED
            ),
            CalculatedExtraction.Status.READY: (
                NotificationType.MOONMINING_EXTRACTION_FINISHED
            ),
            CalculatedExtraction.Status.COMPLETED: (
                NotificationType.MOONMINING_LASER_FIRED
            ),
            CalculatedExtraction.Status.CANCELED: (
                NotificationType.MOONMINING_EXTRACTION_CANCELLED
            ),
        }
        try:
            return status_map[self.extraction.status]
        except KeyError:
            raise ValueError(f"Invalid status: {self.extraction.status}") from None

    @factory.lazy_attribute
    def details(self):
        def _details_link(character: EveEntity) -> str:
            return f'<a href="showinfo:1379//{character.id}">{character.name}</a>'

        def _to_ore_volume_by_type(extraction):
            return {str(obj.ore_type_id): obj.volume for obj in extraction.products}

        if self.create_products:
            self.extraction.products = _generate_calculated_extraction_products(
                self.extraction
            )

        data = {
            "moonID": self.moon_id,
            "structureID": self.extraction.refinery_id,
            "solarSystemID": self.solar_system_id,
            "structureLink": (
                f'<a href="showinfo:35835//{self.extraction.refinery_id}">{self.structure_name}</a>'
            ),
            "structureName": self.structure_name,
            "structureTypeID": self.structure_type_id,
        }
        if self.extraction.status == CalculatedExtraction.Status.STARTED:
            started_by = (
                EveEntityCharacterFactory(id=self.extraction.started_by)
                if self.extraction.started_by
                else EveEntityCharacterFactory()
            )
            data.update(
                {
                    "autoTime": datetime_to_ldap(self.extraction.auto_fracture_at),
                    "readyTime": datetime_to_ldap(self.extraction.chunk_arrival_at),
                    "startedBy": started_by.id,
                    "startedByLink": _details_link(started_by),
                    "oreVolumeByType": _to_ore_volume_by_type(self.extraction),
                }
            )
        elif self.extraction.status == CalculatedExtraction.Status.READY:
            data.update(
                {
                    "autoTime": datetime_to_ldap(self.extraction.auto_fracture_at),
                    "oreVolumeByType": _to_ore_volume_by_type(self.extraction),
                }
            )
        elif self.extraction.status == CalculatedExtraction.Status.COMPLETED:
            data.update(
                {
                    "oreVolumeByType": _to_ore_volume_by_type(self.extraction),
                }
            )

        elif self.extraction.status == CalculatedExtraction.Status.COMPLETED:
            fired_by = (
                EveEntityCharacterFactory(id=self.extraction.fractured_by)
                if self.extraction.fractured_by
                else EveEntityCharacterFactory()
            )
            data.update(
                {
                    "firedBy": fired_by.id,
                    "firedByLink": _details_link(fired_by),
                    "oreVolumeByType": _to_ore_volume_by_type(self.extraction),
                }
            )
        elif self.extraction.status == CalculatedExtraction.Status.CANCELED:
            canceled_by = (
                EveEntityCharacterFactory(id=self.extraction.canceled_by)
                if self.extraction.canceled_by
                else EveEntityCharacterFactory()
            )
            data.update(
                {
                    "cancelledBy": canceled_by.id,
                    "cancelledByLink": _details_link(canceled_by),
                }
            )
        return data
