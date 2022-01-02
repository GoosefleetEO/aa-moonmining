import json

from eveuniverse.models import EveMoon, EveType
from eveuniverse.tools.testdata import load_testdata_from_dict

from . import test_data_filename


def _load_eveuniverse_from_file():
    with open(test_data_filename(), "r", encoding="utf-8") as f:
        data = json.load(f)

    return data


eveuniverse_testdata = _load_eveuniverse_from_file()


def load_eveuniverse():
    load_testdata_from_dict(eveuniverse_testdata)


def nearest_celestial_stub(eve_solar_system, x, y, z, group_id=None):
    eve_type = EveType.objects.get(id=14)
    if (x, y, z) == (55028384780, 7310316270, -163686684205):
        return eve_solar_system.NearestCelestial(
            eve_type=eve_type,
            eve_object=EveMoon.objects.get(id=40161708),  # Auga V - Moon 1
            distance=123,
        )
    elif (x, y, z) == (45028384780, 6310316270, -163686684205):
        return eve_solar_system.NearestCelestial(
            eve_type=eve_type,
            eve_object=EveMoon.objects.get(id=40161709),  # Auga V - Moon 2
            distance=123,
        )
    return None
