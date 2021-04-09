import datetime as dt
from unittest.mock import patch

import pytz

from django.utils.timezone import now
from eveuniverse.models import EveMarketPrice, EveMoon, EveType

from allianceauth.eveonline.models import EveCorporationInfo
from app_utils.esi_testing import BravadoOperationStub
from app_utils.testing import NoSocketsTestCase

from ..models import (
    EveOreType,
    Extraction,
    ExtractionProduct,
    MiningLedgerRecord,
    Moon,
    MoonProduct,
    NotificationType,
    OreQualityClass,
    OreRarityClass,
    Owner,
    Refinery,
)
from . import helpers
from .testdata.esi_client_stub import esi_client_stub
from .testdata.load_allianceauth import load_allianceauth
from .testdata.load_eveuniverse import load_eveuniverse, nearest_celestial_stub

MODELS_PATH = "moonmining.models"


class TestEveOreTypeCalcRefinedValues(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()

    def setUp(self) -> None:
        self.cinnebar = EveOreType.objects.get(id=45506)
        tungsten = EveType.objects.get(id=16637)
        mercury = EveType.objects.get(id=16646)
        evaporite_deposits = EveType.objects.get(id=16635)
        EveMarketPrice.objects.create(eve_type=tungsten, average_price=7000)
        EveMarketPrice.objects.create(eve_type=mercury, average_price=9750)
        EveMarketPrice.objects.create(eve_type=evaporite_deposits, average_price=950)

    def test_should_return_value_for_volume(self):
        self.assertEqual(
            self.cinnebar.calc_refined_value_by_volume(1000000, 0.7), 400225000.0
        )

    def test_should_return_value_per_unit(self):
        self.assertEqual(self.cinnebar.calc_refined_value_per_unit(0.7), 4002.25)


class TestEveOreTypeProfileUrl(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()

    def test_should_return_correct_value(self):
        # given
        cinnebar = EveOreType.objects.get(id=45506)
        # when
        result = cinnebar.profile_url
        # then
        self.assertEqual(result, "https://www.kalkoken.org/apps/eveitems/?typeId=45506")


@patch(MODELS_PATH + ".MOONMINING_VOLUME_PER_MONTH", 1000000)
@patch(MODELS_PATH + ".MOONMINING_REPROCESSING_YIELD", 0.7)
class TestMoonUpdateValue(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        cls.moon = helpers.create_moon_40161708()

    def test_should_calc_correct_value(self):
        # given
        tungsten = EveType.objects.get(id=16637)
        EveMarketPrice.objects.create(eve_type=tungsten, average_price=7000)
        mercury = EveType.objects.get(id=16646)
        EveMarketPrice.objects.create(eve_type=mercury, average_price=9750)
        evaporite_deposits = EveType.objects.get(id=16635)
        EveMarketPrice.objects.create(eve_type=evaporite_deposits, average_price=950)
        pyerite = EveType.objects.get(id=35)
        EveMarketPrice.objects.create(eve_type=pyerite, average_price=10)
        zydrine = EveType.objects.get(id=39)
        EveMarketPrice.objects.create(eve_type=zydrine, average_price=1.7)
        megacyte = EveType.objects.get(id=40)
        EveMarketPrice.objects.create(eve_type=megacyte, average_price=640)
        tritanium = EveType.objects.get(id=34)
        EveMarketPrice.objects.create(eve_type=tritanium, average_price=5)
        mexallon = EveType.objects.get(id=36)
        EveMarketPrice.objects.create(eve_type=mexallon, average_price=117)
        # when
        result = self.moon.calc_value()
        # then
        self.assertEqual(result, 180498825.5)

    def test_should_return_0_if_prices_are_missing(self):
        # given
        EveMarketPrice.objects.create(
            eve_type=EveType.objects.get(id=45506), average_price=1, adjusted_price=2
        )
        # when
        result = self.moon.calc_value()
        # then
        self.assertEqual(result, 0)


class TestExtractionProduct(NoSocketsTestCase):
    def test_should_calculate_value_estimate(self):
        # given
        load_eveuniverse()
        load_allianceauth()
        moon = helpers.create_moon_40161708()
        helpers.add_refinery(moon)
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
        obj = ExtractionProduct.objects.first()
        # when
        result = obj.calc_value()
        # then
        self.assertIsNotNone(result)


@patch(MODELS_PATH + ".esi")
class TestOwnerUpdateRefineries(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()
        _, character_ownership = helpers.create_default_user_1001()
        cls.owner = Owner.objects.create(
            corporation=EveCorporationInfo.objects.get(corporation_id=2001),
            character_ownership=character_ownership,
        )

    @patch(
        MODELS_PATH + ".EveSolarSystem.nearest_celestial", new=nearest_celestial_stub
    )
    def test_should_create_two_new_refineries(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        my_eve_moon = EveMoon.objects.get(id=40161708)
        # when
        self.owner.update_refineries_from_esi()
        # then
        refinery = Refinery.objects.get(id=1000000000001)
        self.assertEqual(refinery.name, "Auga - Paradise Alpha")
        self.assertEqual(refinery.moon.eve_moon, my_eve_moon)

    @patch(
        MODELS_PATH + ".EveSolarSystem.nearest_celestial", new=nearest_celestial_stub
    )
    def test_should_handle_OSError_exceptions_from_universe_structure(self, mock_esi):
        # given
        mock_esi.client.Corporation.get_corporations_corporation_id_structures.return_value = BravadoOperationStub(
            [
                {"type_id": 35835, "structure_id": 1000000000001},
                {"type_id": 35835, "structure_id": 1000000000002},
            ]
        )
        mock_esi.client.Universe.get_universe_structures_structure_id.side_effect = (
            OSError
        )
        # when
        self.owner.update_refineries_from_esi()
        # then
        self.assertEqual(
            mock_esi.client.Universe.get_universe_structures_structure_id.call_count, 2
        )

    @patch(MODELS_PATH + ".EveSolarSystem.nearest_celestial")
    def test_should_handle_OSError_exceptions_from_nearest_celestial(
        self, mock_nearest_celestial, mock_esi
    ):
        # given
        mock_esi.client = esi_client_stub
        mock_nearest_celestial.side_effect = OSError
        # when
        self.owner.update_refineries_from_esi()
        # then
        refinery = Refinery.objects.get(id=1000000000001)
        self.assertIsNone(refinery.moon)
        self.assertEqual(mock_nearest_celestial.call_count, 2)

    @patch(
        MODELS_PATH + ".EveSolarSystem.nearest_celestial", new=nearest_celestial_stub
    )
    def test_should_remove_refineries_that_no_longer_exist(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        Refinery.objects.create(
            id=1990000000001,
            moon=None,
            owner=self.owner,
            eve_type=helpers.eve_type_athanor(),
        )
        # when
        self.owner.update_refineries_from_esi()
        # then
        self.assertSetEqual(
            set(self.owner.refineries.values_list("id", flat=True)),
            {1000000000001, 1000000000002},
        )


@patch(MODELS_PATH + ".esi")
class TestOwnerUpdateMiningLedger(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()
        helpers.generate_eve_entities_from_allianceauth()
        cls.moon = helpers.create_moon_40161708()
        _, character_ownership = helpers.create_default_user_from_evecharacter(1001)
        cls.owner = Owner.objects.create(
            corporation=EveCorporationInfo.objects.get(corporation_id=2001),
            character_ownership=character_ownership,
        )

    def test_should_return_observer_ids_from_esi(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        # when
        result = self.owner.fetch_mining_ledger_observers_from_esi()
        # then
        self.assertSetEqual(result, {1000000000001, 1000000000002})

    def test_should_create_new_mining_ledger(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        refinery = Refinery.objects.create(
            id=1000000000001,
            name="Test",
            moon=self.moon,
            owner=self.owner,
            eve_type=helpers.eve_type_athanor(),
        )
        # when
        refinery.update_mining_ledger_from_esi()
        # then
        self.assertEqual(refinery.mining_ledger.count(), 2)
        obj = refinery.mining_ledger.get(character_id=1001)
        self.assertEqual(obj.day, dt.date(2017, 9, 19))
        self.assertEqual(obj.quantity, 500)
        self.assertEqual(obj.corporation_id, 2001)
        self.assertEqual(obj.ore_type_id, 45506)

    def test_should_update_existing_mining_ledger(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        refinery = Refinery.objects.create(
            id=1000000000001,
            name="Test",
            moon=self.moon,
            owner=self.owner,
            eve_type=helpers.eve_type_athanor(),
        )
        MiningLedgerRecord.objects.create(
            refinery=refinery,
            character_id=1001,
            day=dt.date(2017, 9, 19),
            ore_type_id=45506,
            corporation_id=2001,
            quantity=199,
        )
        # when
        refinery.update_mining_ledger_from_esi()
        # then
        self.assertEqual(refinery.mining_ledger.count(), 2)
        obj = refinery.mining_ledger.get(character_id=1001)
        self.assertEqual(obj.quantity, 500)


@patch(MODELS_PATH + ".esi")
class TestOwnerUpdateExtractions(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()
        helpers.generate_eve_entities_from_allianceauth()
        cls.moon = helpers.create_moon_40161708()

    def test_should_create_started_extraction_with_products(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        _, character_ownership = helpers.create_default_user_from_evecharacter(1001)
        owner = Owner.objects.create(
            corporation=EveCorporationInfo.objects.get(corporation_id=2001),
            character_ownership=character_ownership,
        )
        owner.fetch_notifications_from_esi()
        refinery = Refinery.objects.create(
            id=1000000000001,
            name="Test",
            moon=self.moon,
            owner=owner,
            eve_type=helpers.eve_type_athanor(),
        )
        # when
        owner.update_extractions()
        # then
        self.assertEqual(refinery.extractions.count(), 1)
        extraction = refinery.extractions.first()
        self.assertEqual(extraction.status, Extraction.Status.STARTED)
        self.assertEqual(
            extraction.chunk_arrival_at,
            dt.datetime(2021, 4, 15, 18, 0, tzinfo=pytz.UTC),
        )
        self.assertEqual(extraction.started_by_id, 1001)
        self.assertEqual(extraction.products.count(), 4)
        product = extraction.products.get(ore_type_id=45506)
        self.assertEqual(product.volume, 1288475.124715103)
        product = extraction.products.get(ore_type_id=46676)
        self.assertEqual(product.volume, 544691.7637724016)
        product = extraction.products.get(ore_type_id=22)
        self.assertEqual(product.volume, 526825.4047522942)
        product = extraction.products.get(ore_type_id=46689)
        self.assertEqual(product.volume, 528996.6386983792)
        self.assertIsNotNone(extraction.value)
        self.assertIsNotNone(extraction.is_jackpot)


@patch(MODELS_PATH + ".esi")
class TestOwnerUpdateExtractionsFromEsi(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()
        helpers.generate_eve_entities_from_allianceauth()
        cls.moon = helpers.create_moon_40161708()

    def test_should_create_started_extraction(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        _, character_ownership = helpers.create_default_user_from_evecharacter(1001)
        owner = Owner.objects.create(
            corporation=EveCorporationInfo.objects.get(corporation_id=2001),
            character_ownership=character_ownership,
        )
        refinery = Refinery.objects.create(
            id=1000000000001,
            name="Test",
            moon=self.moon,
            owner=owner,
            eve_type=helpers.eve_type_athanor(),
        )
        # when
        owner.update_extractions_from_esi()
        # then
        self.assertEqual(refinery.extractions.count(), 1)
        extraction = refinery.extractions.first()
        self.assertEqual(extraction.status, Extraction.Status.STARTED)
        self.assertEqual(
            extraction.chunk_arrival_at,
            dt.datetime(2021, 4, 15, 18, 0, tzinfo=pytz.UTC),
        )
        self.assertEqual(
            extraction.started_at, dt.datetime(2021, 4, 1, 12, 00, tzinfo=pytz.UTC)
        )
        self.assertEqual(
            extraction.auto_fracture_at,
            dt.datetime(2021, 4, 15, 21, 00, tzinfo=pytz.UTC),
        )
        self.assertEqual(extraction.products.count(), 0)
        self.assertIsNone(extraction.value)
        self.assertIsNone(extraction.is_jackpot)

    def test_should_create_completed_extraction(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        _, character_ownership = helpers.create_default_user_from_evecharacter(1001)
        owner = Owner.objects.create(
            corporation=EveCorporationInfo.objects.get(corporation_id=2001),
            character_ownership=character_ownership,
        )
        refinery = Refinery.objects.create(
            id=1000000000001,
            name="Test",
            moon=self.moon,
            owner=owner,
            eve_type=helpers.eve_type_athanor(),
        )
        # when
        with patch(MODELS_PATH + ".now") as mock_now:
            mock_now.return_value = dt.datetime(2021, 4, 18, 18, 15, 0, tzinfo=pytz.UTC)
            owner.update_extractions_from_esi()
        # then
        self.assertEqual(refinery.extractions.count(), 1)
        extraction = refinery.extractions.first()
        self.assertEqual(extraction.status, Extraction.Status.COMPLETED)

    def test_should_identify_canceled_extractions(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        _, character_ownership = helpers.create_default_user_from_evecharacter(1001)
        owner = Owner.objects.create(
            corporation=EveCorporationInfo.objects.get(corporation_id=2001),
            character_ownership=character_ownership,
        )
        refinery = Refinery.objects.create(
            id=1000000000001,
            name="Test",
            moon=self.moon,
            owner=owner,
            eve_type=helpers.eve_type_athanor(),
        )
        started_extraction = Extraction.objects.create(
            refinery=refinery,
            started_at=dt.datetime(2021, 3, 10, 18, 0, tzinfo=pytz.UTC),
            chunk_arrival_at=dt.datetime(2021, 3, 15, 18, 0, tzinfo=pytz.UTC),
            auto_fracture_at=dt.datetime(2021, 3, 15, 21, 0, tzinfo=pytz.UTC),
            status=Extraction.Status.STARTED,
        )
        # when
        with patch(MODELS_PATH + ".now") as mock_now:
            mock_now.return_value = dt.datetime(2021, 4, 1, 12, 0, tzinfo=pytz.UTC)
            owner.update_extractions_from_esi()
        # then
        started_extraction.refresh_from_db()
        self.assertEqual(started_extraction.status, Extraction.Status.CANCELED)
        self.assertTrue(started_extraction.canceled_at)


@patch(MODELS_PATH + ".esi")
class TestOwnerUpdateExtractionsFromNotifications(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()
        helpers.generate_eve_entities_from_allianceauth()
        cls.moon = helpers.create_moon_40161708()

    def test_should_create_canceled_extraction_with_products(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        _, character_ownership = helpers.create_default_user_from_evecharacter(1001)
        owner = Owner.objects.create(
            corporation=EveCorporationInfo.objects.get(corporation_id=2001),
            character_ownership=character_ownership,
        )
        owner.fetch_notifications_from_esi()
        refinery = Refinery.objects.create(
            id=1000000000002,
            name="Test",
            moon=self.moon,
            owner=owner,
            eve_type=helpers.eve_type_athanor(),
        )
        extraction = Extraction.objects.create(
            refinery=refinery,
            chunk_arrival_at=dt.datetime(2021, 4, 15, 18, 0, tzinfo=pytz.UTC),
            started_at=dt.datetime(2021, 4, 10, 18, 0, tzinfo=pytz.UTC),
            auto_fracture_at=dt.datetime(2021, 4, 15, 21, 0, tzinfo=pytz.UTC),
        )
        # when
        owner.update_extractions_from_notifications()
        # then
        self.assertEqual(refinery.extractions.count(), 1)
        extraction.refresh_from_db()
        self.assertEqual(extraction.status, Extraction.Status.CANCELED)
        self.assertEqual(
            extraction.canceled_at,
            dt.datetime(2019, 11, 22, 2, tzinfo=pytz.UTC),
        )
        self.assertEqual(extraction.canceled_by_id, 1001)
        self.assertEqual(
            set(extraction.products.values_list("ore_type_id", flat=True)),
            {45506, 46676, 22, 46689},
        )

    def test_should_create_finished_extraction_with_products(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        _, character_ownership = helpers.create_default_user_from_evecharacter(1001)
        owner = Owner.objects.create(
            corporation=EveCorporationInfo.objects.get(corporation_id=2001),
            character_ownership=character_ownership,
        )
        owner.fetch_notifications_from_esi()
        refinery = Refinery.objects.create(
            id=1000000000003,
            name="Test",
            moon=self.moon,
            owner=owner,
            eve_type=helpers.eve_type_athanor(),
        )
        extraction = Extraction.objects.create(
            refinery=refinery,
            chunk_arrival_at=dt.datetime(2021, 4, 15, 18, 0, tzinfo=pytz.UTC),
            started_at=dt.datetime(2021, 4, 10, 18, 0, tzinfo=pytz.UTC),
            auto_fracture_at=dt.datetime(2021, 4, 15, 21, 0, tzinfo=pytz.UTC),
        )
        ExtractionProduct.objects.create(
            extraction=extraction, ore_type_id=45506, volume=1288475
        )
        ExtractionProduct.objects.create(
            extraction=extraction, ore_type_id=46676, volume=544691
        )
        ExtractionProduct.objects.create(
            extraction=extraction, ore_type_id=22, volume=526825
        )
        ExtractionProduct.objects.create(
            extraction=extraction, ore_type_id=46689, volume=528996
        )
        # when
        owner.update_extractions_from_notifications()
        # then
        self.assertEqual(refinery.extractions.count(), 1)
        extraction.refresh_from_db()
        self.assertEqual(extraction.status, Extraction.Status.READY)
        self.assertEqual(
            set(extraction.products.values_list("ore_type_id", flat=True)),
            {46311, 46676, 46678, 46689},
        )

    def test_should_create_manually_fractured_extraction_with_products(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        _, character_ownership = helpers.create_default_user_from_evecharacter(1001)
        owner = Owner.objects.create(
            corporation=EveCorporationInfo.objects.get(corporation_id=2001),
            character_ownership=character_ownership,
        )
        owner.fetch_notifications_from_esi()
        refinery = Refinery.objects.create(
            id=1000000000004,
            name="Test",
            moon=self.moon,
            owner=owner,
            eve_type=helpers.eve_type_athanor(),
        )
        extraction = Extraction.objects.create(
            refinery=refinery,
            chunk_arrival_at=dt.datetime(2021, 4, 15, 18, 0, tzinfo=pytz.UTC),
            started_at=dt.datetime(2021, 4, 10, 18, 0, tzinfo=pytz.UTC),
            auto_fracture_at=dt.datetime(2021, 4, 15, 21, 0, tzinfo=pytz.UTC),
        )
        ExtractionProduct.objects.create(
            extraction=extraction, ore_type_id=45506, volume=1288475
        )
        ExtractionProduct.objects.create(
            extraction=extraction, ore_type_id=46676, volume=544691
        )
        ExtractionProduct.objects.create(
            extraction=extraction, ore_type_id=22, volume=526825
        )
        ExtractionProduct.objects.create(
            extraction=extraction, ore_type_id=46689, volume=528996
        )
        # when
        owner.update_extractions_from_notifications()
        # then
        self.assertEqual(refinery.extractions.count(), 1)
        extraction.refresh_from_db()
        self.assertEqual(extraction.status, Extraction.Status.COMPLETED)
        self.assertEqual(extraction.fractured_by_id, 1001)
        self.assertEqual(
            set(extraction.products.values_list("ore_type_id", flat=True)),
            {46311, 46676, 46678, 46689},
        )

    def test_should_create_auto_fractured_extraction_with_products(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        _, character_ownership = helpers.create_default_user_from_evecharacter(1001)
        owner = Owner.objects.create(
            corporation=EveCorporationInfo.objects.get(corporation_id=2001),
            character_ownership=character_ownership,
        )
        owner.fetch_notifications_from_esi()
        refinery = Refinery.objects.create(
            id=1000000000005,
            name="Test",
            moon=self.moon,
            owner=owner,
            eve_type=helpers.eve_type_athanor(),
        )
        extraction = Extraction.objects.create(
            refinery=refinery,
            chunk_arrival_at=dt.datetime(2021, 4, 15, 18, 0, tzinfo=pytz.UTC),
            started_at=dt.datetime(2021, 4, 10, 18, 0, tzinfo=pytz.UTC),
            auto_fracture_at=dt.datetime(2021, 4, 15, 21, 0, tzinfo=pytz.UTC),
        )
        ExtractionProduct.objects.create(
            extraction=extraction, ore_type_id=45506, volume=1288475
        )
        ExtractionProduct.objects.create(
            extraction=extraction, ore_type_id=46676, volume=544691
        )
        ExtractionProduct.objects.create(
            extraction=extraction, ore_type_id=22, volume=526825
        )
        ExtractionProduct.objects.create(
            extraction=extraction, ore_type_id=46689, volume=528996
        )
        # when
        owner.update_extractions_from_notifications()
        # then
        self.assertEqual(refinery.extractions.count(), 1)
        extraction.refresh_from_db()
        self.assertEqual(extraction.status, Extraction.Status.COMPLETED)
        self.assertIsNone(extraction.fractured_by)
        self.assertEqual(
            set(extraction.products.values_list("ore_type_id", flat=True)),
            {46311, 46676, 46678},
        )

    def test_should_cancel_existing_extraction(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        _, character_ownership = helpers.create_default_user_from_evecharacter(1002)
        owner = Owner.objects.create(
            corporation=EveCorporationInfo.objects.get(corporation_id=2001),
            character_ownership=character_ownership,
        )
        owner.fetch_notifications_from_esi()
        refinery = Refinery.objects.create(
            id=1000000000001,
            moon=self.moon,
            owner=owner,
            name="Test",
            eve_type=helpers.eve_type_athanor(),
        )
        extraction = Extraction.objects.create(
            refinery=refinery,
            chunk_arrival_at=dt.datetime(2021, 4, 15, 18, 0, tzinfo=pytz.UTC),
            started_at=dt.datetime(2021, 4, 10, 18, 0, tzinfo=pytz.UTC),
            auto_fracture_at=dt.datetime(2021, 4, 15, 21, 0, tzinfo=pytz.UTC),
        )
        # when
        owner.update_extractions_from_notifications()
        # then
        self.assertEqual(refinery.extractions.count(), 1)
        extraction.refresh_from_db()
        self.assertEqual(extraction.status, Extraction.Status.CANCELED)

    def test_should_cancel_existing_and_update_two_other(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        _, character_ownership = helpers.create_default_user_from_evecharacter(1004)
        owner = Owner.objects.create(
            corporation=EveCorporationInfo.objects.get(corporation_id=2001),
            character_ownership=character_ownership,
        )
        owner.fetch_notifications_from_esi()
        refinery = Refinery.objects.create(
            id=1000000000001,
            moon=self.moon,
            owner=owner,
            name="Test",
            eve_type=helpers.eve_type_athanor(),
        )
        ready_time_1 = dt.datetime(2019, 11, 21, 10, tzinfo=pytz.UTC)
        ready_time_2 = dt.datetime(2019, 11, 21, 11, tzinfo=pytz.UTC)
        ready_time_3 = dt.datetime(2019, 11, 21, 12, tzinfo=pytz.UTC)
        extraction_1 = Extraction.objects.create(
            refinery=refinery,
            chunk_arrival_at=ready_time_1,
            started_at=ready_time_1 - dt.timedelta(days=14),
            auto_fracture_at=ready_time_1 + dt.timedelta(hours=4),
            status=Extraction.Status.STARTED,
        )
        extraction_2 = Extraction.objects.create(
            refinery=refinery,
            chunk_arrival_at=ready_time_2,
            started_at=ready_time_2 - dt.timedelta(days=14),
            auto_fracture_at=ready_time_2 + dt.timedelta(hours=4),
            status=Extraction.Status.STARTED,
        )
        ExtractionProduct.objects.create(
            extraction=extraction_2, ore_type_id=45506, volume=1288475
        )
        ExtractionProduct.objects.create(
            extraction=extraction_2, ore_type_id=46676, volume=544691
        )
        ExtractionProduct.objects.create(
            extraction=extraction_2, ore_type_id=22, volume=526825
        )
        ExtractionProduct.objects.create(
            extraction=extraction_2, ore_type_id=46689, volume=528996
        )
        extraction_3 = Extraction.objects.create(
            refinery=refinery,
            chunk_arrival_at=ready_time_3,
            started_at=ready_time_3 - dt.timedelta(days=14),
            auto_fracture_at=ready_time_3 + dt.timedelta(hours=4),
            status=Extraction.Status.STARTED,
        )
        # when
        owner.update_extractions_from_notifications()
        # then
        self.assertEqual(refinery.extractions.count(), 3)
        extraction_1.refresh_from_db()
        self.assertEqual(extraction_1.status, Extraction.Status.CANCELED)
        extraction_2.refresh_from_db()
        self.assertEqual(extraction_2.status, Extraction.Status.COMPLETED)
        self.assertEqual(
            set(extraction_2.products.values_list("ore_type_id", flat=True)),
            {46311, 46676, 46678, 46689},
        )
        extraction_3.refresh_from_db()
        self.assertEqual(extraction_3.status, Extraction.Status.STARTED)
        self.assertEqual(
            set(extraction_3.products.values_list("ore_type_id", flat=True)),
            {45506, 46676, 22, 46689},
        )

    def test_should_update_refinery_with_moon_from_notification_if_not_found(
        self, mock_esi
    ):
        # given
        mock_esi.client = esi_client_stub
        _, character_ownership = helpers.create_default_user_from_evecharacter(1001)
        owner = Owner.objects.create(
            corporation=EveCorporationInfo.objects.get(corporation_id=2001),
            character_ownership=character_ownership,
        )
        owner.fetch_notifications_from_esi()
        Refinery.objects.create(
            id=1000000000001,
            moon=None,
            owner=owner,
            eve_type=helpers.eve_type_athanor(),
        )
        # when
        owner.update_extractions()
        # then
        obj = Refinery.objects.get(id=1000000000001)
        self.assertEqual(obj.moon, self.moon)


@patch(MODELS_PATH + ".esi")
class TestOwnerFetchNotifications(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()
        helpers.generate_eve_entities_from_allianceauth()

    def test_should_create_new_notifications_from_esi(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        _, character_ownership = helpers.create_default_user_from_evecharacter(1005)
        owner = Owner.objects.create(
            corporation=EveCorporationInfo.objects.get(corporation_id=2001),
            character_ownership=character_ownership,
        )
        # when
        owner.fetch_notifications_from_esi()
        # then
        self.assertEqual(owner.notifications.count(), 5)
        obj = owner.notifications.get(notification_id=1005000101)
        self.assertEqual(obj.notif_type, NotificationType.MOONMINING_EXTRACTION_STARTED)
        self.assertEqual(obj.sender_id, 2101)
        self.assertEqual(
            obj.timestamp, dt.datetime(2019, 11, 22, 1, 0, tzinfo=pytz.UTC)
        )
        self.assertEqual(obj.details["moonID"], 40161708)
        self.assertEqual(obj.details["structureID"], 1000000000001)


class TestMoonCalcRarityClass(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        cls.ore_type_r0 = EveOreType.objects.get(id=46676)
        cls.ore_type_r4 = EveOreType.objects.get(id=45492)
        cls.ore_type_r8 = EveOreType.objects.get(id=45497)
        cls.ore_type_r16 = EveOreType.objects.get(id=46296)
        cls.ore_type_r32 = EveOreType.objects.get(id=45506)
        cls.ore_type_r64 = EveOreType.objects.get(id=46316)

    def test_should_return_R4(self):
        # given
        moon = Moon.objects.create(eve_moon_id=40161708)
        MoonProduct.objects.create(moon=moon, ore_type=self.ore_type_r0, amount=0.23)
        MoonProduct.objects.create(moon=moon, ore_type=self.ore_type_r4, amount=0.19)
        # when
        result = moon.calc_rarity_class()
        # then
        self.assertEqual(result, OreRarityClass.R4)

    def test_should_return_R8(self):
        # given
        moon = Moon.objects.create(eve_moon_id=40161708)
        MoonProduct.objects.create(moon=moon, ore_type=self.ore_type_r8, amount=0.25)
        MoonProduct.objects.create(moon=moon, ore_type=self.ore_type_r0, amount=0.23)
        MoonProduct.objects.create(moon=moon, ore_type=self.ore_type_r4, amount=0.19)
        # when
        result = moon.calc_rarity_class()
        # then
        self.assertEqual(result, OreRarityClass.R8)

    def test_should_return_R16(self):
        # given
        moon = Moon.objects.create(eve_moon_id=40161708)
        MoonProduct.objects.create(moon=moon, ore_type=self.ore_type_r4, amount=0.19)
        MoonProduct.objects.create(moon=moon, ore_type=self.ore_type_r16, amount=0.23)
        MoonProduct.objects.create(moon=moon, ore_type=self.ore_type_r8, amount=0.25)
        # when
        result = moon.calc_rarity_class()
        # then
        self.assertEqual(result, OreRarityClass.R16)

    def test_should_return_R32(self):
        # given
        moon = Moon.objects.create(eve_moon_id=40161708)
        MoonProduct.objects.create(moon=moon, ore_type=self.ore_type_r16, amount=0.23)
        MoonProduct.objects.create(moon=moon, ore_type=self.ore_type_r32, amount=0.19)
        MoonProduct.objects.create(moon=moon, ore_type=self.ore_type_r8, amount=0.25)
        # when
        result = moon.calc_rarity_class()
        # then
        self.assertEqual(result, OreRarityClass.R32)

    def test_should_return_R64(self):
        # given
        moon = Moon.objects.create(eve_moon_id=40161708)
        MoonProduct.objects.create(moon=moon, ore_type=self.ore_type_r16, amount=0.23)
        MoonProduct.objects.create(moon=moon, ore_type=self.ore_type_r32, amount=0.19)
        MoonProduct.objects.create(moon=moon, ore_type=self.ore_type_r64, amount=0.25)
        # when
        result = moon.calc_rarity_class()
        # then
        self.assertEqual(result, OreRarityClass.R64)


class TestOreQualityClass(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()

    def test_should_return_correct_quality(self):
        # given
        ore_quality_regular = EveOreType.objects.get(id=45490)
        ore_quality_improved = EveOreType.objects.get(id=46280)
        ore_quality_excellent = EveOreType.objects.get(id=46281)
        # when/then
        self.assertEqual(ore_quality_regular.quality_class, OreQualityClass.REGULAR)
        self.assertEqual(ore_quality_improved.quality_class, OreQualityClass.IMPROVED)
        self.assertEqual(ore_quality_excellent.quality_class, OreQualityClass.EXCELLENT)

    def test_should_return_correct_tag(self):
        self.assertIn("+100%", OreQualityClass.EXCELLENT.bootstrap_tag_html)


class TestExtractionIsJackpot(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()
        moon = helpers.create_moon_40161708()
        owner = Owner.objects.create(
            corporation=EveCorporationInfo.objects.get(corporation_id=2001)
        )
        cls.refinery = Refinery.objects.create(
            id=40161708, moon=moon, owner=owner, eve_type_id=35835
        )
        cls.ore_quality_regular = EveOreType.objects.get(id=45490)
        cls.ore_quality_improved = EveOreType.objects.get(id=46280)
        cls.ore_quality_excellent = EveOreType.objects.get(id=46281)
        cls.ore_quality_excellent_2 = EveOreType.objects.get(id=46283)

    def test_should_be_jackpot(self):
        # given
        extraction = Extraction.objects.create(
            refinery=self.refinery,
            chunk_arrival_at=now() + dt.timedelta(days=3),
            auto_fracture_at=now() + dt.timedelta(days=4),
            started_at=now() - dt.timedelta(days=3),
            status=Extraction.Status.STARTED,
        )
        ExtractionProduct.objects.create(
            extraction=extraction,
            ore_type=self.ore_quality_excellent,
            volume=1000000 * 0.1,
        )
        ExtractionProduct.objects.create(
            extraction=extraction,
            ore_type=self.ore_quality_excellent_2,
            volume=1000000 * 0.1,
        )
        # when
        result = extraction.calc_is_jackpot()
        # then
        self.assertTrue(result)

    def test_should_not_be_jackpot_1(self):
        # given
        extraction = Extraction.objects.create(
            refinery=self.refinery,
            chunk_arrival_at=now() + dt.timedelta(days=3),
            auto_fracture_at=now() + dt.timedelta(days=4),
            started_at=now() - dt.timedelta(days=3),
            status=Extraction.Status.STARTED,
        )
        ExtractionProduct.objects.create(
            extraction=extraction,
            ore_type=self.ore_quality_excellent,
            volume=1000000 * 0.1,
        )
        ExtractionProduct.objects.create(
            extraction=extraction,
            ore_type=self.ore_quality_improved,
            volume=1000000 * 0.1,
        )
        # when
        result = extraction.calc_is_jackpot()
        # then
        self.assertFalse(result)

    def test_should_not_be_jackpot_2(self):
        # given
        extraction = Extraction.objects.create(
            refinery=self.refinery,
            chunk_arrival_at=now() + dt.timedelta(days=3),
            auto_fracture_at=now() + dt.timedelta(days=4),
            started_at=now() - dt.timedelta(days=3),
            status=Extraction.Status.STARTED,
        )
        ExtractionProduct.objects.create(
            extraction=extraction,
            ore_type=self.ore_quality_improved,
            volume=1000000 * 0.1,
        )
        ExtractionProduct.objects.create(
            extraction=extraction,
            ore_type=self.ore_quality_excellent,
            volume=1000000 * 0.1,
        )
        # when
        result = extraction.calc_is_jackpot()
        # then
        self.assertFalse(result)

    def test_should_not_be_jackpot_3(self):
        # given
        extraction = Extraction.objects.create(
            refinery=self.refinery,
            chunk_arrival_at=now() + dt.timedelta(days=3),
            auto_fracture_at=now() + dt.timedelta(days=4),
            started_at=now() - dt.timedelta(days=3),
            status=Extraction.Status.STARTED,
        )
        ExtractionProduct.objects.create(
            extraction=extraction,
            ore_type=self.ore_quality_regular,
            volume=1000000 * 0.1,
        )
        ExtractionProduct.objects.create(
            extraction=extraction,
            ore_type=self.ore_quality_improved,
            volume=1000000 * 0.1,
        )
        # when
        result = extraction.calc_is_jackpot()
        # then
        self.assertFalse(result)

    def test_should_not_be_jackpot_4(self):
        # given
        extraction = Extraction.objects.create(
            refinery=self.refinery,
            chunk_arrival_at=now() + dt.timedelta(days=3),
            auto_fracture_at=now() + dt.timedelta(days=4),
            started_at=now() - dt.timedelta(days=3),
            status=Extraction.Status.STARTED,
        )
        # when
        result = extraction.calc_is_jackpot()
        # then
        self.assertFalse(result)
