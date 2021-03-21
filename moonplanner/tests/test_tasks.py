import datetime as dt
from unittest.mock import patch

from app_utils.testing import NoSocketsTestCase, create_user_from_evecharacter

from django.test import TestCase
from django.utils.timezone import now

from allianceauth.eveonline.models import EveCharacter, EveCorporationInfo
from eveuniverse.models import EveMarketPrice, EveMoon, EveSolarSystem, EveType

from .. import tasks
from ..models import MiningCorporation, Moon, Refinery
from . import helpers
from .testdata.esi_client_stub import esi_client_stub
from .testdata.load_allianceauth import load_allianceauth
from .testdata.load_eveuniverse import load_eveuniverse
from .testdata.survey_data import fetch_survey_data

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
        refinery = Refinery.objects.get(id=1000000000001)
        self.assertEqual(refinery.name, "Auga - Paradise Alpha")
        self.assertEqual(refinery.moon.eve_moon, my_eve_moon)

    def test_should_update_refinery_with_moon_from_notification_if_not_found(
        self, mock_esi, mock_nearest_celestial
    ):
        # given
        mock_esi.client = esi_client_stub
        my_eve_moon = EveMoon.objects.get(id=40161708)
        mock_nearest_celestial.return_value = None
        # when
        tasks.run_refineries_update(self.mining_corporation.pk)
        # then
        refinery = Refinery.objects.get(id=1000000000001)
        self.assertEqual(refinery.name, "Auga - Paradise Alpha")
        self.assertEqual(refinery.moon.eve_moon, my_eve_moon)

    # TODO: test when refinery does not exist for notification
    # TODO: tests for extractions


class TestProcessSurveyInput(TestCase):
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
        cls.survey_data = fetch_survey_data()

    def test_should_process_survey_normally(self):
        # when
        result = tasks.process_survey_input(self.survey_data.get(2), self.user.pk)
        # then
        self.assertTrue(result)
        m1 = Moon.objects.get(pk=40161708)
        self.assertEqual(m1.products_updated_by, self.user)
        self.assertAlmostEqual(m1.products_updated_at, now(), delta=dt.timedelta(30))
        self.assertEqual(m1.products.count(), 4)
        self.assertEqual(m1.products.get(eve_type_id=45506).amount, 0.19)
        self.assertEqual(m1.products.get(eve_type_id=46676).amount, 0.23)
        self.assertEqual(m1.products.get(eve_type_id=46678).amount, 0.25)
        self.assertEqual(m1.products.get(eve_type_id=46689).amount, 0.33)

        m2 = Moon.objects.get(pk=40161709)
        self.assertEqual(m1.products_updated_by, self.user)
        self.assertAlmostEqual(m1.products_updated_at, now(), delta=dt.timedelta(30))
        self.assertEqual(m2.products.count(), 4)
        self.assertEqual(m2.products.get(eve_type_id=45492).amount, 0.27)
        self.assertEqual(m2.products.get(eve_type_id=45494).amount, 0.23)
        self.assertEqual(m2.products.get(eve_type_id=46676).amount, 0.21)
        self.assertEqual(m2.products.get(eve_type_id=46678).amount, 0.29)

    def test_should_handle_bad_data_orderly(self):
        # when
        result = tasks.process_survey_input(self.survey_data.get(3))
        # then
        self.assertFalse(result)

    @patch(MODULE_PATH + ".notify")
    def test_notification_on_success(self, mock_notify):
        result = tasks.process_survey_input(self.survey_data.get(2), self.user.pk)
        self.assertTrue(result)
        self.assertTrue(mock_notify.called)
        _, kwargs = mock_notify.call_args
        self.assertEqual(kwargs["user"], self.user)
        self.assertEqual(kwargs["level"], "success")

    @patch(MODULE_PATH + ".notify")
    def test_notification_on_error_1(self, mock_notify):
        result = tasks.process_survey_input("invalid input", self.user.pk)
        self.assertFalse(result)
        self.assertTrue(mock_notify.called)
        _, kwargs = mock_notify.call_args
        self.assertEqual(kwargs["user"], self.user)
        self.assertEqual(kwargs["level"], "danger")


@patch(MODULE_PATH + ".EveMarketPrice.objects.update_from_esi", new=lambda: None)
class TestUpdateMoonIncome(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        cls.moon = helpers.create_moon()
        EveMarketPrice.objects.create(
            eve_type=EveType.objects.get(id=45506), average_price=1, adjusted_price=2
        )
        EveMarketPrice.objects.create(
            eve_type=EveType.objects.get(id=46676), average_price=2, adjusted_price=3
        )
        EveMarketPrice.objects.create(
            eve_type=EveType.objects.get(id=46678), average_price=3, adjusted_price=4
        )
        EveMarketPrice.objects.create(
            eve_type=EveType.objects.get(id=46689), average_price=4, adjusted_price=5
        )

    def test_should_update_all(self):
        # when
        tasks.update_moon_income()
        # then
        ...  # TODO: add asserts
