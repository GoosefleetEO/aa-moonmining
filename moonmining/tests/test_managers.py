import datetime as dt
from unittest.mock import patch

import pytz

from django.test import TestCase
from django.utils.timezone import now
from eveuniverse.models import EveMarketPrice, EveType

from app_utils.testing import NoSocketsTestCase

from ..models import EveOreType, Extraction, Moon, Refinery
from . import helpers
from .testdata.factories import ExtractionFactory, OwnerFactory, RefineryFactory
from .testdata.load_allianceauth import load_allianceauth
from .testdata.load_eveuniverse import load_eveuniverse
from .testdata.survey_data import fetch_survey_data

MANAGERS_PATH = "moonmining.managers"


class TestEveOreTypeManager(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()

    @patch(MANAGERS_PATH + ".MOONMINING_USE_REPROCESS_PRICING", False)
    def test_should_update_current_prices_with_market_price(self):
        # given
        ore_type = EveOreType.objects.get(name="Cinnabar")
        EveMarketPrice.objects.create(eve_type_id=ore_type.id, average_price=42)
        # when
        EveOreType.objects.update_current_prices()
        # then
        self.assertEqual(ore_type.extras.current_price, 42)

    @patch(MANAGERS_PATH + ".MOONMINING_REPROCESSING_YIELD", 0.7)
    @patch(MANAGERS_PATH + ".MOONMINING_USE_REPROCESS_PRICING", True)
    def test_should_update_current_prices_with_reprocessed_value(self):
        # given
        ore_type = EveOreType.objects.get(name="Cinnabar")
        tungsten = EveType.objects.get(id=16637)
        mercury = EveType.objects.get(id=16646)
        evaporite_deposits = EveType.objects.get(id=16635)
        EveMarketPrice.objects.create(eve_type=tungsten, average_price=7000)
        EveMarketPrice.objects.create(eve_type=mercury, average_price=9750)
        EveMarketPrice.objects.create(eve_type=evaporite_deposits, average_price=950)
        # when
        EveOreType.objects.update_current_prices()
        # then
        self.assertEqual(ore_type.extras.current_price, 4002.25)


class TestExtractionManager(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()
        helpers.generate_eve_entities_from_allianceauth()

    def test_should_update_completed(self):
        # given
        refinery = RefineryFactory()
        extraction_1 = ExtractionFactory(
            refinery=refinery,
            started_at=dt.datetime(2021, 1, 1, 1, 0, tzinfo=pytz.UTC),
            chunk_arrival_at=dt.datetime(2021, 1, 1, 12, 0, tzinfo=pytz.UTC),
            auto_fracture_at=dt.datetime(2021, 1, 1, 15, 0, tzinfo=pytz.UTC),
            status=Extraction.Status.STARTED,
            create_products=False,
        )
        extraction_2 = ExtractionFactory(
            refinery=refinery,
            started_at=dt.datetime(2021, 1, 1, 2, 0, tzinfo=pytz.UTC),
            chunk_arrival_at=dt.datetime(2021, 1, 1, 15, 0, tzinfo=pytz.UTC),
            auto_fracture_at=dt.datetime(2021, 1, 1, 18, 0, tzinfo=pytz.UTC),
            status=Extraction.Status.STARTED,
            create_products=False,
        )
        extraction_3 = ExtractionFactory(
            refinery=refinery,
            started_at=dt.datetime(2021, 1, 1, 3, 0, tzinfo=pytz.UTC),
            chunk_arrival_at=dt.datetime(2021, 1, 1, 18, 0, tzinfo=pytz.UTC),
            auto_fracture_at=dt.datetime(2021, 1, 1, 21, 0, tzinfo=pytz.UTC),
            status=Extraction.Status.STARTED,
            create_products=False,
        )
        extraction_4 = ExtractionFactory(
            refinery=refinery,
            started_at=dt.datetime(2021, 1, 1, 4, 0, tzinfo=pytz.UTC),
            chunk_arrival_at=dt.datetime(2021, 1, 1, 4, 0, tzinfo=pytz.UTC),
            auto_fracture_at=dt.datetime(2021, 1, 1, 7, 0, tzinfo=pytz.UTC),
            status=Extraction.Status.CANCELED,
            create_products=False,
        )
        # when
        with patch(MANAGERS_PATH + ".now") as mock_now:
            mock_now.return_value = dt.datetime(2021, 1, 1, 15, 30, tzinfo=pytz.UTC)
            Extraction.objects.all().update_status()
        # then
        extraction_1.refresh_from_db()
        self.assertEqual(extraction_1.status, Extraction.Status.COMPLETED)
        extraction_2.refresh_from_db()
        self.assertEqual(extraction_2.status, Extraction.Status.READY)
        extraction_3.refresh_from_db()
        self.assertEqual(extraction_3.status, Extraction.Status.STARTED)
        extraction_4.refresh_from_db()
        self.assertEqual(extraction_4.status, Extraction.Status.CANCELED)


class TestProcessSurveyInput(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()
        cls.user, cls.character_ownership = helpers.create_user_from_evecharacter(
            1001,
            permissions=[
                "moonmining.basic_access",
                "moonmining.extractions_access",
                "moonmining.add_refinery_owner",
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
        result = Moon.objects.update_moons_from_survey(
            self.survey_data.get(2), self.user
        )
        # then
        self.assertTrue(result)
        m1 = Moon.objects.get(pk=40161708)
        self.assertEqual(m1.products_updated_by, self.user)
        self.assertAlmostEqual(m1.products_updated_at, now(), delta=dt.timedelta(30))
        self.assertEqual(m1.products.count(), 4)
        self.assertEqual(m1.products.get(ore_type_id=45506).amount, 0.19)
        self.assertEqual(m1.products.get(ore_type_id=46676).amount, 0.23)
        self.assertEqual(m1.products.get(ore_type_id=46678).amount, 0.25)
        self.assertEqual(m1.products.get(ore_type_id=46689).amount, 0.33)

        m2 = Moon.objects.get(pk=40161709)
        self.assertEqual(m2.products_updated_by, self.user)
        self.assertAlmostEqual(m2.products_updated_at, now(), delta=dt.timedelta(30))
        self.assertEqual(m2.products.count(), 4)
        self.assertEqual(m2.products.get(ore_type_id=45492).amount, 0.27)
        self.assertEqual(m2.products.get(ore_type_id=45494).amount, 0.23)
        self.assertEqual(m2.products.get(ore_type_id=46676).amount, 0.21)
        self.assertEqual(m2.products.get(ore_type_id=46678).amount, 0.29)


class TestRefineryManager(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()
        helpers.generate_eve_entities_from_allianceauth()

    def test_should_return_ids(self):
        # given
        owner = OwnerFactory()
        RefineryFactory(id=1001, owner=owner)
        RefineryFactory(id=1002, owner=owner)
        # when
        result = Refinery.objects.ids()
        # then
        self.assertSetEqual(result, {1001, 1002})
