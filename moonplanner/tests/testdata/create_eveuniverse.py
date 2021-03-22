from django.test import TestCase
from eveuniverse.models import EveType
from eveuniverse.tools.testdata import ModelSpec, create_testdata

from moonplanner import constants

from . import test_data_filename


class CreateEveUniverseTestData(TestCase):
    def test_create_testdata(self):
        testdata_spec = [
            ModelSpec(
                "EveGroup", ids=[constants.EVE_GROUP_ID_MOON], include_children=True
            ),
            ModelSpec(
                "EveCategory",
                ids=[constants.EVE_CATEGORY_ID_ASTEROID],
                include_children=True,
                enabled_sections=[EveType.Section.TYPE_MATERIALS],
            ),
            ModelSpec(
                "EveType",
                ids=[
                    35834,  # Keepstar
                    35835,  # Athanor,
                ],
            ),
            ModelSpec(
                "EveMoon",
                ids=[
                    40161708,  # Auga V - Moon 1
                    40161709,  # Auga V - Moon 2
                    40131695,  # Helgatild IX - Moon 12
                ],
            ),
        ]
        create_testdata(testdata_spec, test_data_filename())
