import json

from django.http import JsonResponse
from eveuniverse.models import EveEntity, EveMarketPrice, EveType

from allianceauth.eveonline.models import EveCharacter
from app_utils.testing import create_user_from_evecharacter, response_text

from ..constants import EveTypeId
from ..models import EveOreType, Owner


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

    EveMarketPrice.objects.create(eve_type_id=EveTypeId.CHROMITE, average_price=2_000)
    EveMarketPrice.objects.create(eve_type_id=EveTypeId.EUXENITE, average_price=1_300)
    EveMarketPrice.objects.create(eve_type_id=EveTypeId.XENOTIME, average_price=10_000)
    EveOreType.objects.update_current_prices(use_process_pricing=use_process_pricing)


def json_response_to_python_2(response: JsonResponse, data_key="data") -> object:
    """Convert JSON response into Python object."""
    data = json.loads(response_text(response))
    return data[data_key]


def json_response_to_dict_2(response: JsonResponse, key="id", data_key="data") -> dict:
    """Convert JSON response into dict by given key."""
    return {x[key]: x for x in json_response_to_python_2(response, data_key)}
