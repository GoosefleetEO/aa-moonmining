import datetime as dt
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.timezone import now
from django_webtest import WebTest
from eveuniverse.models import EveMarketPrice, EveType

from app_utils.testing import create_user_from_evecharacter

from .. import tasks
from ..models import MiningCorporation, Moon, Refinery
from . import helpers
from .testdata.esi_client_stub import esi_client_stub
from .testdata.load_allianceauth import load_allianceauth
from .testdata.load_eveuniverse import load_eveuniverse, nearest_celestial_stub
from .testdata.survey_data import fetch_survey_data

MANAGERS_PATH = "moonplanner.managers"
MODELS_PATH = "moonplanner.models"
TASKS_PATH = "moonplanner.tasks"
VIEWS_PATH = "moonplanner.views"


class TestUI(WebTest):
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
            ],
        )

    def test_should_open_extractions(self):
        # given
        self.app.set_user(self.user)
        # when
        index = self.app.get(reverse("moonplanner:extractions"))
        # then
        self.assertEqual(index.status_code, 200)

    # TODO: Add more UI tests


@override_settings(CELERY_ALWAYS_EAGER=True)
class TestUpdateTasks(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()
        _, cls.character_ownership = helpers.create_default_user_1001()

    @patch(
        MODELS_PATH + ".EveSolarSystem.nearest_celestial", new=nearest_celestial_stub
    )
    @patch(MODELS_PATH + ".esi")
    def test_should_update_all_mining_corporations(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        moon = helpers.create_moon_40161708()
        helpers.create_corporation_from_character_ownership(self.character_ownership)
        # when
        tasks.update_all_mining_corporations.delay()
        # then
        moon.refresh_from_db()
        self.assertSetEqual(
            helpers.model_ids(MiningCorporation, "eve_corporation__corporation_id"),
            {2001},
        )
        self.assertSetEqual(helpers.model_ids(Refinery), {1000000000001, 1000000000002})
        self.assertEqual(Refinery.objects.first().extractions.count(), 1)
        # TODO: add more tests

    @patch(TASKS_PATH + ".EveMarketPrice.objects.update_from_esi")
    def test_should_update_income_for_all_moons(self, mock_update_prices):
        # given
        mock_update_prices.return_value = None
        moon = helpers.create_moon_40161708()
        tungsten = EveType.objects.get(id=16637)
        mercury = EveType.objects.get(id=16646)
        evaporite_deposits = EveType.objects.get(id=16635)
        EveMarketPrice.objects.create(eve_type=tungsten, average_price=7000)
        EveMarketPrice.objects.create(eve_type=mercury, average_price=9750)
        EveMarketPrice.objects.create(eve_type=evaporite_deposits, average_price=950)
        # when
        tasks.update_all_moon_values.delay()
        # then
        moon.refresh_from_db()
        self.assertIsNotNone(moon.value)


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

    @patch(MANAGERS_PATH + ".notify", new=lambda *args, **kwargs: None)
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

    @patch(MANAGERS_PATH + ".notify", new=lambda *args, **kwargs: None)
    def test_should_handle_bad_data_orderly(self):
        # when
        result = tasks.process_survey_input(self.survey_data.get(3))
        # then
        self.assertFalse(result)

    @patch(MANAGERS_PATH + ".notify")
    def test_notification_on_success(self, mock_notify):
        result = tasks.process_survey_input(self.survey_data.get(2), self.user.pk)
        self.assertTrue(result)
        self.assertTrue(mock_notify.called)
        _, kwargs = mock_notify.call_args
        self.assertEqual(kwargs["user"], self.user)
        self.assertEqual(kwargs["level"], "success")

    @patch(MANAGERS_PATH + ".notify")
    def test_notification_on_error_1(self, mock_notify):
        result = tasks.process_survey_input("invalid input", self.user.pk)
        self.assertFalse(result)
        self.assertTrue(mock_notify.called)
        _, kwargs = mock_notify.call_args
        self.assertEqual(kwargs["user"], self.user)
        self.assertEqual(kwargs["level"], "danger")
