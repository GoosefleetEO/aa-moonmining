import datetime as dt
from unittest.mock import patch

import pytz

from django.test import TestCase
from django.utils.timezone import now

from allianceauth.eveonline.models import EveCorporationInfo
from app_utils.testing import NoSocketsTestCase

from ..models import Extraction, Moon, Owner, Refinery
from . import helpers
from .testdata.load_allianceauth import load_allianceauth
from .testdata.load_eveuniverse import load_eveuniverse
from .testdata.survey_data import fetch_survey_data

MANAGERS_PATH = "moonmining.managers"


class TestExtractionManager(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()
        helpers.generate_eve_entities_from_allianceauth()
        cls.moon = helpers.create_moon_40161708()

    def setUp(self) -> None:
        owner = Owner.objects.create(
            corporation=EveCorporationInfo.objects.get(corporation_id=2001),
        )
        self.refinery = Refinery.objects.create(
            id=1000000000001,
            name="Test",
            moon=self.moon,
            owner=owner,
            eve_type=helpers.eve_type_athanor(),
        )

    def test_should_update_completed(self):
        # given
        extraction_1 = Extraction.objects.create(
            refinery=self.refinery,
            started_at=dt.datetime(2021, 1, 1, 1, 0, tzinfo=pytz.UTC),
            chunk_arrival_at=dt.datetime(2021, 1, 1, 12, 0, tzinfo=pytz.UTC),
            auto_fracture_at=dt.datetime(2021, 1, 1, 15, 0, tzinfo=pytz.UTC),
            status=Extraction.Status.STARTED,
        )
        extraction_2 = Extraction.objects.create(
            refinery=self.refinery,
            started_at=dt.datetime(2021, 1, 1, 2, 0, tzinfo=pytz.UTC),
            chunk_arrival_at=dt.datetime(2021, 1, 1, 15, 0, tzinfo=pytz.UTC),
            auto_fracture_at=dt.datetime(2021, 1, 1, 18, 0, tzinfo=pytz.UTC),
            status=Extraction.Status.STARTED,
        )
        extraction_3 = Extraction.objects.create(
            refinery=self.refinery,
            started_at=dt.datetime(2021, 1, 1, 3, 0, tzinfo=pytz.UTC),
            chunk_arrival_at=dt.datetime(2021, 1, 1, 18, 0, tzinfo=pytz.UTC),
            auto_fracture_at=dt.datetime(2021, 1, 1, 21, 0, tzinfo=pytz.UTC),
            status=Extraction.Status.STARTED,
        )
        extraction_4 = Extraction.objects.create(
            refinery=self.refinery,
            started_at=dt.datetime(2021, 1, 1, 4, 0, tzinfo=pytz.UTC),
            chunk_arrival_at=dt.datetime(2021, 1, 1, 4, 0, tzinfo=pytz.UTC),
            auto_fracture_at=dt.datetime(2021, 1, 1, 7, 0, tzinfo=pytz.UTC),
            status=Extraction.Status.CANCELED,
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
        cls.owner = Owner.objects.create(
            corporation=EveCorporationInfo.objects.get(corporation_id=2001),
        )

    def test_should_return_ids(self):
        # given
        Refinery.objects.create(
            id=1001,
            name="Test",
            owner=self.owner,
            eve_type=helpers.eve_type_athanor(),
        )
        Refinery.objects.create(
            id=1002,
            name="Test",
            owner=self.owner,
            eve_type=helpers.eve_type_athanor(),
        )
        # when
        result = Refinery.objects.ids()
        # then
        self.assertSetEqual(result, {1001, 1002})
