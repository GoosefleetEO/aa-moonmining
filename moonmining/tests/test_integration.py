import datetime as dt
from unittest.mock import patch

import pytz

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.timezone import now
from django_webtest import WebTest
from eveuniverse.models import EveMoon

from app_utils.esi import EsiStatus
from app_utils.testing import NoSocketsTestCase, create_user_from_evecharacter

from .. import tasks
from ..models import Owner, Refinery
from . import helpers
from .testdata.esi_client_stub import esi_client_stub
from .testdata.factories import (
    ExtractionFactory,
    MoonFactory,
    OwnerFactory,
    RefineryFactory,
)
from .testdata.load_allianceauth import load_allianceauth
from .testdata.load_eveuniverse import load_eveuniverse, nearest_celestial_stub
from .testdata.survey_data import fetch_survey_data

MANAGERS_PATH = "moonmining.managers"
MODELS_PATH = "moonmining.models"
TASKS_PATH = "moonmining.tasks"
VIEWS_PATH = "moonmining.views"


class TestUI(WebTest):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()
        cls.user, cls.character_ownership = create_user_from_evecharacter(
            1001,
            permissions=["moonmining.basic_access", "moonmining.extractions_access"],
        )

    def test_should_open_extractions(self):
        # given
        self.app.set_user(self.user)
        # when
        index = self.app.get(reverse("moonmining:extractions"))
        # then
        self.assertEqual(index.status_code, 200)

    # TODO: Add more UI tests


@patch(TASKS_PATH + ".fetch_esi_status", lambda: EsiStatus(True, 100, 60))
@patch(MODELS_PATH + ".EveSolarSystem.nearest_celestial", new=nearest_celestial_stub)
@override_settings(CELERY_ALWAYS_EAGER=True, CELERY_EAGER_PROPAGATES_EXCEPTIONS=True)
class TestUpdateTasks(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()
        helpers.generate_eve_entities_from_allianceauth()
        helpers.generate_market_prices()
        _, cls.character_ownership = helpers.create_default_user_from_evecharacter(1001)

    @patch(MODELS_PATH + ".esi")
    def test_should_update_all_mining_corporations(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        MoonFactory(eve_moon=EveMoon.objects.get(id=40161708))
        corporation_2001 = OwnerFactory(character_ownership=self.character_ownership)
        # when
        tasks.run_regular_updates.delay()
        # then
        self.assertSetEqual(Refinery.objects.ids(), {1000000000001, 1000000000002})
        refinery = Refinery.objects.get(id=1000000000001)
        self.assertEqual(refinery.extractions.count(), 1)
        corporation_2001.refresh_from_db()
        self.assertAlmostEqual(
            corporation_2001.last_update_at, now(), delta=dt.timedelta(minutes=1)
        )
        self.assertTrue(corporation_2001.last_update_ok)

    @patch(MODELS_PATH + ".esi")
    def test_should_report_when_updating_mining_corporations_failed(self, mock_esi):
        # given
        mock_esi.client.Corporation.get_corporations_corporation_id_structures.side_effect = (
            OSError
        )
        corporation_2001 = OwnerFactory(character_ownership=self.character_ownership)
        # when
        try:
            tasks.run_regular_updates.delay()
        except OSError:
            pass
        # then
        corporation_2001.refresh_from_db()
        self.assertAlmostEqual(
            corporation_2001.last_update_at, now(), delta=dt.timedelta(minutes=1)
        )
        self.assertIsNone(corporation_2001.last_update_ok)

        # TODO: add more tests

    @patch(MODELS_PATH + ".esi")
    def test_should_not_update_disabled_corporation(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        MoonFactory(eve_moon=EveMoon.objects.get(id=40161708))
        corporation_2001 = OwnerFactory(character_ownership=self.character_ownership)
        _, character_ownership_1003 = create_user_from_evecharacter(
            1003,
            permissions=[
                "moonmining.basic_access",
                "moonmining.extractions_access",
                "moonmining.add_refinery_owner",
            ],
            scopes=Owner.esi_scopes(),
        )
        corporation_2002 = OwnerFactory(
            character_ownership=character_ownership_1003, last_update_ok=None
        )
        my_date = dt.datetime(2020, 1, 11, 12, 30, tzinfo=pytz.UTC)
        corporation_2002.last_update_at = my_date
        corporation_2002.is_enabled = False
        corporation_2002.save()
        # when
        tasks.run_regular_updates.delay()
        # then
        corporation_2001.refresh_from_db()
        self.assertAlmostEqual(
            corporation_2001.last_update_at, now(), delta=dt.timedelta(minutes=1)
        )
        self.assertTrue(corporation_2001.last_update_ok)
        corporation_2002.refresh_from_db()
        self.assertEqual(corporation_2002.last_update_at, my_date)
        self.assertIsNone(corporation_2002.last_update_ok)

    @patch(MODELS_PATH + ".esi")
    def test_should_update_mining_ledgers(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        owner_2001 = OwnerFactory(character_ownership=self.character_ownership)
        refinery_1 = RefineryFactory(id=1000000000001, owner=owner_2001)
        refinery_2 = RefineryFactory(id=1000000000002, owner=owner_2001)
        _, ownership_1003 = helpers.create_default_user_from_evecharacter(1003)
        owner_2002 = OwnerFactory(character_ownership=ownership_1003)
        refinery_11 = RefineryFactory.create(id=1000000000011, owner=owner_2002)
        # when
        tasks.run_report_updates()
        # then
        self.assertEqual(refinery_1.mining_ledger.count(), 2)
        self.assertEqual(refinery_2.mining_ledger.count(), 1)
        self.assertEqual(refinery_11.mining_ledger.count(), 1)

    @patch(TASKS_PATH + ".EveMarketPrice.objects.update_from_esi")
    def test_should_update_all_calculated_values(self, mock_update_prices):
        # given
        mock_update_prices.return_value = None
        moon = MoonFactory()
        owner = OwnerFactory(character_ownership=self.character_ownership)
        refinery = RefineryFactory(moon=moon, owner=owner)
        extraction = ExtractionFactory(refinery=refinery)
        # when
        tasks.run_calculated_properties_update.delay()
        # then
        moon.refresh_from_db()
        extraction.refresh_from_db()
        self.assertIsNotNone(moon.value)
        self.assertIsNotNone(extraction.value)
        ore = extraction.products.first().ore_type
        self.assertIsNotNone(ore.extras.current_price)


class TestProcessSurveyInput(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()
        cls.user, cls.character_ownership = create_user_from_evecharacter(
            1001,
            permissions=[
                "moonmining.basic_access",
                "moonmining.extractions_access",
                "moonmining.add_refinery_owner",
            ],
            scopes=Owner.esi_scopes(),
        )
        cls.survey_data = fetch_survey_data()

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
