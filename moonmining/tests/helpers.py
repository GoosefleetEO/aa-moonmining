import datetime as dt

from django.db import models
from django.utils.timezone import now
from eveuniverse.models import EveEntity, EveMoon, EveType

from allianceauth.eveonline.models import EveCharacter, EveCorporationInfo
from app_utils.testing import create_user_from_evecharacter

from ..app_settings import MOONMINING_VOLUME_PER_MONTH
from ..models import Extraction, ExtractionProduct, Moon, MoonProduct, Owner, Refinery


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


def create_owner_from_character_ownership(
    character_ownership,
) -> Owner:
    owner, _ = Owner.objects.get_or_create(
        corporation=EveCorporationInfo.objects.get(
            corporation_id=character_ownership.character.corporation_id
        ),
        character_ownership=character_ownership,
    )
    return owner


def add_refinery(moon: Moon, owner: Owner = None) -> Refinery:
    if not owner:
        owner, _ = Owner.objects.get_or_create(
            corporation=EveCorporationInfo.objects.get(corporation_id=2001)
        )
    refinery = Refinery.objects.create(
        id=moon.eve_moon_id,
        moon=moon,
        owner=owner,
        eve_type=EveType.objects.get(id=35835),
    )
    extraction = Extraction.objects.create(
        refinery=refinery,
        chunk_arrival_at=now() + dt.timedelta(days=3),
        auto_fracture_at=now() + dt.timedelta(days=3, hours=12),
        started_at=now() - dt.timedelta(days=3),
        status=Extraction.Status.STARTED,
    )
    for product in moon.products.all():
        ExtractionProduct.objects.create(
            extraction=extraction,
            ore_type=product.ore_type,
            volume=MOONMINING_VOLUME_PER_MONTH * product.amount,
        )
    return refinery


def create_default_user_from_evecharacter(character_id):
    return create_user_from_evecharacter(
        character_id,
        permissions=[
            "moonmining.basic_access",
            "moonmining.upload_moon_scan",
            "moonmining.extractions_access",
            "moonmining.add_refinery_owner",
        ],
        scopes=Owner.esi_scopes(),
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
