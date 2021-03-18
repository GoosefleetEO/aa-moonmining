from unittest.mock import patch

from app_utils.testing import NoSocketsTestCase, create_user_from_evecharacter

from allianceauth.eveonline.models import EveCharacter, EveCorporationInfo
from eveuniverse.models import EveMoon, EveSolarSystem, EveType

from .. import tasks
from ..models import MiningCorporation, Refinery
from .testdata.esi_client_stub import esi_client_stub
from .testdata.load_allianceauth import load_allianceauth
from .testdata.load_eveuniverse import load_eveuniverse

MODULE_PATH = "moonplanner.tasks"


@patch(MODULE_PATH + ".EveSolarSystem.nearest_celestial")
@patch(MODULE_PATH + ".esi")
class TestRunRefineriesUpdate(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()
        cls.user, cls.character_ownership = create_user_from_evecharacter(
            1001,
            permissions=[
                "moonplanner.access_moonplanner",
                "moonplanner.access_our_moons",
                "moonplanner.add_mining_corporation",
            ],
            scopes=[
                "esi-industry.read_corporation_mining.v1",
                "esi-universe.read_structures.v1",
                "esi-characters.read_notifications.v1",
                "esi-corporations.read_structures.v1",
            ],
        )
        cls.mining_corporation = MiningCorporation.objects.create(
            corporation=EveCorporationInfo.objects.get(corporation_id=2001),
            character=EveCharacter.objects.get(character_id=1001),
        )

    def test_should_create_new(self, mock_esi, mock_nearest_celestial):
        # given
        mock_esi.client = esi_client_stub
        my_eve_moon = EveMoon.objects.get(id=40161708)
        mock_nearest_celestial.return_value = EveSolarSystem.NearestCelestial(
            eve_type=EveType.objects.get(id=14), eve_object=my_eve_moon, distance=123
        )
        # when
        tasks.run_refineries_update(self.mining_corporation.pk)
        # then
        refinery = Refinery.objects.get(structure_id=1000000000001)
        self.assertEqual(refinery.name, "Auga - Paradise Alpha")
        self.assertEqual(refinery.eve_moon, my_eve_moon)

    # TODO: test when refinery does not exist for notification


# class TestTasks(TestCase):
#     @classmethod
#     def setUpClass(cls):
#         super(TestTasks, cls).setUpClass()
#         EveRegion.objects.create(region_id=10000030, region_name="Heimatar")
#         EveSolarSystem.objects.create(
#             region_id=10000030, solar_system_id=30002542, solar_system_name="Auga"
#         )
#         EveType.objects.create(type_id=45506, type_name="Cinnabar")
#         EveType.objects.create(type_id=46676, type_name="Cubic Bistot")
#         EveType.objects.create(type_id=46678, type_name="Flawless Arkonor")
#         EveType.objects.create(type_id=45492, type_name="Bitumens")
#         EveType.objects.create(type_id=46689, type_name="Stable Veldspar")
#         EveType.objects.create(type_id=45494, type_name="Cobaltite")
#         EveType.objects.create(type_id=14, type_name="Moon")
#         EveItem.objects.create(item_id=40161708)
#         EveItemDenormalized.objects.create(
#             item_id=40161708,
#             item_name="Auga V - Moon 1",
#             type_id=14,
#             solar_system_id=30002542,
#         )
#         EveItem.objects.create(item_id=40161709)
#         EveItemDenormalized.objects.create(
#             item_id=40161709,
#             item_name="Auga V - Moon 2",
#             type_id=14,
#             solar_system_id=30002542,
#         )
#         cls.survey_data = survey_data()
#         cls.user = AuthUtils.create_user("Bruce Wayne")

#     def test_process_resources(self):
#         # process 2 times: first against empty DB,
#         # second against existing objects
#         for x in range(2):
#             self.assertTrue(tasks.process_survey_input(self.survey_data.get(2)))

#             m1 = MoonIncome.objects.get(pk=40161708)
#             self.assertEqual(m1.moonproduct_set.count(), 4)
#             self.assertEqual(m1.moonproduct_set.get(ore_type_id=45506).amount, 0.19)
#             self.assertEqual(m1.moonproduct_set.get(ore_type_id=46676).amount, 0.23)
#             self.assertEqual(m1.moonproduct_set.get(ore_type_id=46678).amount, 0.25)
#             self.assertEqual(m1.moonproduct_set.get(ore_type_id=46689).amount, 0.33)

#             m2 = MoonIncome.objects.get(pk=40161709)
#             self.assertEqual(m2.moonproduct_set.count(), 4)
#             self.assertEqual(m2.moonproduct_set.get(ore_type_id=45492).amount, 0.27)
#             self.assertEqual(m2.moonproduct_set.get(ore_type_id=45494).amount, 0.23)
#             self.assertEqual(m2.moonproduct_set.get(ore_type_id=46676).amount, 0.21)
#             self.assertEqual(m2.moonproduct_set.get(ore_type_id=46678).amount, 0.29)

#     def test_process_resources_bad_data(self):
#         self.assertFalse(tasks.process_survey_input(self.survey_data.get(3)))

#     @patch(MODULE_PATH + ".notify")
#     def test_notification_on_success(self, mock_notify):
#         result = tasks.process_survey_input(self.survey_data.get(2), self.user.pk)
#         self.assertTrue(result)
#         self.assertTrue(mock_notify.called)
#         _, kwargs = mock_notify.call_args
#         self.assertEqual(kwargs["user"], self.user)
#         self.assertEqual(kwargs["level"], "success")

#     @patch(MODULE_PATH + ".notify")
#     def test_notification_on_error_1(self, mock_notify):
#         result = tasks.process_survey_input("invalid input", self.user.pk)
#         self.assertFalse(result)
#         self.assertTrue(mock_notify.called)
#         _, kwargs = mock_notify.call_args
#         self.assertEqual(kwargs["user"], self.user)
#         self.assertEqual(kwargs["level"], "danger")
