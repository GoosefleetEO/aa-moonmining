import datetime as dt
import json

from django.http import JsonResponse
from django.utils.timezone import now
from eveuniverse.models import EveEntity, EveMarketPrice, EveMoon, EveType

from allianceauth.eveonline.models import EveCharacter, EveCorporationInfo
from app_utils.testing import create_user_from_evecharacter, response_text

from ..app_settings import MOONMINING_VOLUME_PER_MONTH
from ..models import (
    EveOreType,
    Extraction,
    ExtractionProduct,
    Moon,
    MoonProduct,
    Owner,
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


def generate_market_prices(use_process_pricing=False):
    tungsten = EveType.objects.get(id=16637)
    EveMarketPrice.objects.create(eve_type=tungsten, average_price=7000)
    mercury = EveType.objects.get(id=16646)
    EveMarketPrice.objects.create(eve_type=mercury, average_price=9750)
    evaporite_deposits = EveType.objects.get(id=16635)
    EveMarketPrice.objects.create(eve_type=evaporite_deposits, average_price=950)
    pyerite = EveType.objects.get(id=35)
    EveMarketPrice.objects.create(eve_type=pyerite, average_price=10)
    zydrine = EveType.objects.get(id=39)
    EveMarketPrice.objects.create(eve_type=zydrine, average_price=1.7)
    megacyte = EveType.objects.get(id=40)
    EveMarketPrice.objects.create(eve_type=megacyte, average_price=640)
    tritanium = EveType.objects.get(id=34)
    EveMarketPrice.objects.create(eve_type=tritanium, average_price=5)
    mexallon = EveType.objects.get(id=36)
    EveMarketPrice.objects.create(eve_type=mexallon, average_price=117.0)
    EveMarketPrice.objects.create(eve_type_id=45506, average_price=2400.0)
    EveMarketPrice.objects.create(eve_type_id=46676, average_price=609.0)
    EveMarketPrice.objects.create(eve_type_id=46678, average_price=310.9)
    EveMarketPrice.objects.create(eve_type_id=46689, average_price=7.7)
    EveOreType.objects.update_current_prices(use_process_pricing=use_process_pricing)


def json_response_to_python_2(response: JsonResponse, data_key="data") -> object:
    """Convert JSON response into Python object."""
    data = json.loads(response_text(response))
    return data[data_key]


def json_response_to_dict_2(response: JsonResponse, key="id", data_key="data") -> dict:
    """Convert JSON response into dict by given key."""
    return {x[key]: x for x in json_response_to_python_2(response, data_key)}
