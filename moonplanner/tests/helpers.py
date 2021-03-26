import datetime as dt

from django.db import models
from django.utils.timezone import now
from eveuniverse.models import EveEntity, EveMoon, EveType

from allianceauth.eveonline.models import EveCharacter, EveCorporationInfo
from app_utils.testing import create_user_from_evecharacter

from ..app_settings import MOONPLANNER_VOLUME_PER_MONTH
from ..models import (
    Extraction,
    ExtractionProduct,
    MiningCorporation,
    Moon,
    MoonProduct,
    Refinery,
)


def create_moon_40161708() -> EveMoon:
    Moon.objects.filter(pk=40161708).delete()
    moon = Moon.objects.create(eve_moon=EveMoon.objects.get(id=40161708))
    MoonProduct.objects.create(
        moon=moon, ore_type=EveType.objects.get(id=45506), amount=0.19
    )
    MoonProduct.objects.create(
        moon=moon, ore_type=EveType.objects.get(id=46676), amount=0.23
    )
    MoonProduct.objects.create(
        moon=moon, ore_type=EveType.objects.get(id=46678), amount=0.25
    )
    MoonProduct.objects.create(
        moon=moon, ore_type=EveType.objects.get(id=46689), amount=0.33
    )
    return moon


def create_corporation_from_character_ownership(character_ownership):
    corporation, _ = MiningCorporation.objects.get_or_create(
        eve_corporation=EveCorporationInfo.objects.get(
            corporation_id=character_ownership.character.corporation_id
        ),
        character_ownership=character_ownership,
    )
    return corporation


def add_refinery(moon: Moon, corporation: MiningCorporation = None) -> Refinery:
    if not corporation:
        corporation, _ = MiningCorporation.objects.get_or_create(
            eve_corporation=EveCorporationInfo.objects.get(corporation_id=2001)
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
            ore_type=product.ore_type,
            volume=MOONPLANNER_VOLUME_PER_MONTH * product.amount,
        )
    return refinery


def create_default_user_from_evecharacter(character_id):
    return create_user_from_evecharacter(
        character_id,
        permissions=[
            "moonplanner.basic_access",
            "moonplanner.upload_moon_scan",
            "moonplanner.access_our_moons",
            "moonplanner.add_corporation",
        ],
        scopes=MiningCorporation.esi_scopes(),
    )


def create_default_user_1001():
    return create_default_user_from_evecharacter(1001)


def eve_type_athanor():
    return EveType.objects.get(id=35835)


def model_ids(MyModel: models.Model, key="pk") -> set:
    """Return all ids of given model as set."""
    return set(MyModel.objects.values_list(key, flat=True))


def generate_eve_entities_from_allianceauth():
    for character in EveCharacter.objects.all():
        EveEntity.objects.create(
            id=character.character_id,
            name=character.character_name,
            category=EveEntity.CATEGORY_CHARACTER,
        )
        EveEntity.objects.get_or_create(
            id=character.corporation_id,
            name=character.corporation_name,
            category=EveEntity.CATEGORY_CORPORATION,
        )
        if character.alliance_id:
            EveEntity.objects.get_or_create(
                id=character.alliance_id,
                name=character.alliance_name,
                category=EveEntity.CATEGORY_ALLIANCE,
            )
