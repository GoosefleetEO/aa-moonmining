from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django_webtest import WebTest
from eveuniverse.models import EveMarketPrice, EveType

from app_utils.testing import create_user_from_evecharacter

from .. import tasks
from ..models import MiningCorporation, Refinery
from . import helpers
from .testdata.esi_client_stub import esi_client_stub
from .testdata.load_allianceauth import load_allianceauth
from .testdata.load_eveuniverse import load_eveuniverse, nearest_celestial_stub

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
class TestMainTasks(TestCase):
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
        tasks.update_all_moon_income.delay()
        # then
        moon.refresh_from_db()
        self.assertIsNotNone(moon.income)
