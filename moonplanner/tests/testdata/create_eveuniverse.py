from django.test import TestCase

from eveuniverse import constants
from eveuniverse.tools.testdata import ModelSpec, create_testdata

from . import test_data_filename


class CreateEveUniverseTestData(TestCase):
    def test_create_testdata(self):
        testdata_spec = [
            ModelSpec(
                "EveGroup", ids=[constants.EVE_GROUP_ID_MOON], include_children=True
            ),
            ModelSpec(
                "EveType",
                ids=[
                    35835,  # Athanor
                    45506,  # Ore types below
                    46676,
                    46678,
                    46689,
                    45492,
                    45494,
                    45495,
                    45491,
                    45510,
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
