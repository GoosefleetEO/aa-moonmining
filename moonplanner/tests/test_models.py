import datetime as dt
from unittest.mock import patch

import pytz

from eveuniverse.models import EveMarketPrice, EveMoon, EveType

from allianceauth.eveonline.models import EveCorporationInfo
from app_utils.esi_testing import BravadoOperationStub
from app_utils.testing import NoSocketsTestCase

from ..models import (
    Extraction,
    ExtractionProduct,
    MiningCorporation,
    Refinery,
    calc_refined_value,
)
from . import helpers
from .testdata.esi_client_stub import esi_client_stub
from .testdata.load_allianceauth import load_allianceauth
from .testdata.load_eveuniverse import load_eveuniverse, nearest_celestial_stub

MODULE_PATH = "moonplanner.models"


class TestCalcRefinedValue(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()

    def test_should_return_correct_value(self):
        # given
        cinnebar = EveType.objects.get(id=45506)
        tungsten = EveType.objects.get(id=16637)
        mercury = EveType.objects.get(id=16646)
        evaporite_deposits = EveType.objects.get(id=16635)
        EveMarketPrice.objects.create(eve_type=tungsten, average_price=7000)
        EveMarketPrice.objects.create(eve_type=mercury, average_price=9750)
        EveMarketPrice.objects.create(eve_type=evaporite_deposits, average_price=950)
        # when
        result = calc_refined_value(cinnebar, 1000000, 0.7)
        # then
        self.assertEqual(result, 400225000.0)


@patch(MODULE_PATH + ".MOONPLANNER_VOLUME_PER_MONTH", 1000000)
@patch(MODULE_PATH + ".MOONPLANNER_REPROCESSING_YIELD", 0.7)
class TestMoonUpdateValue(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        cls.moon = helpers.create_moon_40161708()

    def test_should_update_value(self):
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
        self.moon.update_value()
        # then
        self.moon.refresh_from_db()
        self.assertEqual(self.moon.value, 180498825.5)

    def test_should_set_none_if_prices_are_missing(self):
        # given
        EveMarketPrice.objects.create(
            eve_type=EveType.objects.get(id=45506), average_price=1, adjusted_price=2
        )
        # when
        self.moon.update_value()
        # then
        self.moon.refresh_from_db()
        self.assertIsNone(self.moon.value)


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


@patch(MODULE_PATH + ".esi")
class TestMiningCorporationUpdateRefineries(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()
        _, character_ownership = helpers.create_default_user_1001()
        cls.mining_corporation = MiningCorporation.objects.create(
            eve_corporation=EveCorporationInfo.objects.get(corporation_id=2001),
            character_ownership=character_ownership,
        )

    @patch(
        MODULE_PATH + ".EveSolarSystem.nearest_celestial", new=nearest_celestial_stub
    )
    def test_should_create_two_new_refineries(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        my_eve_moon = EveMoon.objects.get(id=40161708)
        # when
        self.mining_corporation.update_refineries_from_esi()
        # then
        refinery = Refinery.objects.get(id=1000000000001)
        self.assertEqual(refinery.name, "Auga - Paradise Alpha")
        self.assertEqual(refinery.moon.eve_moon, my_eve_moon)

    @patch(
        MODULE_PATH + ".EveSolarSystem.nearest_celestial", new=nearest_celestial_stub
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
        self.mining_corporation.update_refineries_from_esi()
        # then
        self.assertEqual(
            mock_esi.client.Universe.get_universe_structures_structure_id.call_count, 2
        )

    @patch(MODULE_PATH + ".EveSolarSystem.nearest_celestial")
    def test_should_handle_OSError_exceptions_from_nearest_celestial(
        self, mock_nearest_celestial, mock_esi
    ):
        # given
        mock_esi.client = esi_client_stub
        mock_nearest_celestial.side_effect = OSError
        # when
        self.mining_corporation.update_refineries_from_esi()
        # then
        refinery = Refinery.objects.get(id=1000000000001)
        self.assertIsNone(refinery.moon)
        self.assertEqual(mock_nearest_celestial.call_count, 2)

    @patch(
        MODULE_PATH + ".EveSolarSystem.nearest_celestial", new=nearest_celestial_stub
    )
    def test_should_remove_refineries_that_no_longer_exist(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        Refinery.objects.create(
            id=1990000000001,
            moon=None,
            corporation=self.mining_corporation,
            eve_type=helpers.eve_type_athanor(),
        )
        # when
        self.mining_corporation.update_refineries_from_esi()
        # then
        self.assertSetEqual(
            set(self.mining_corporation.refineries.values_list("id", flat=True)),
            {1000000000001, 1000000000002},
        )


@patch(MODULE_PATH + ".esi")
class TestMiningCorporationUpdateExtractions(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()
        helpers.generate_eve_entities_from_allianceauth()
        cls.moon = helpers.create_moon_40161708()

    def test_should_create_new_extraction_with_products(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        _, character_ownership = helpers.create_default_user_from_evecharacter(1001)
        mining_corporation = MiningCorporation.objects.create(
            eve_corporation=EveCorporationInfo.objects.get(corporation_id=2001),
            character_ownership=character_ownership,
        )
        refinery = Refinery.objects.create(
            id=1000000000001,
            moon=self.moon,
            corporation=mining_corporation,
            eve_type=helpers.eve_type_athanor(),
        )
        # when
        mining_corporation.update_extractions_from_esi()
        # then
        self.assertEqual(refinery.extractions.count(), 1)
        extraction = refinery.extractions.first()
        self.assertEqual(
            extraction.ready_time,
            dt.datetime(2019, 11, 20, 0, 1, 0, 105915, tzinfo=pytz.UTC),
        )
        self.assertEqual(
            extraction.auto_time,
            dt.datetime(2019, 11, 20, 3, 1, 0, 105915, tzinfo=pytz.UTC),
        )
        self.assertEqual(extraction.started_by_id, 1001)
        self.assertEqual(extraction.products.count(), 4)
        product = extraction.products.get(eve_type_id=45506)
        self.assertEqual(product.volume, 1288475.124715103)
        product = extraction.products.get(eve_type_id=46676)
        self.assertEqual(product.volume, 544691.7637724016)
        product = extraction.products.get(eve_type_id=46678)
        self.assertEqual(product.volume, 526825.4047522942)
        product = extraction.products.get(eve_type_id=46689)
        self.assertEqual(product.volume, 528996.6386983792)

    def test_should_cancel_existing_extraction(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        _, character_ownership = helpers.create_default_user_from_evecharacter(1002)
        mining_corporation = MiningCorporation.objects.create(
            eve_corporation=EveCorporationInfo.objects.get(corporation_id=2001),
            character_ownership=character_ownership,
        )
        refinery = Refinery.objects.create(
            id=1000000000001,
            moon=self.moon,
            corporation=mining_corporation,
            eve_type=helpers.eve_type_athanor(),
        )
        # when
        mining_corporation.update_extractions_from_esi()
        # then
        self.assertEqual(refinery.extractions.count(), 0)

    def test_should_create_one_new_extraction(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        _, character_ownership = helpers.create_default_user_from_evecharacter(1004)
        mining_corporation = MiningCorporation.objects.create(
            eve_corporation=EveCorporationInfo.objects.get(corporation_id=2001),
            character_ownership=character_ownership,
        )
        refinery = Refinery.objects.create(
            id=1000000000001,
            moon=self.moon,
            corporation=mining_corporation,
            eve_type=helpers.eve_type_athanor(),
        )
        Extraction.objects.create(
            refinery=refinery,
            ready_time=dt.datetime(2019, 11, 20, 0, 1, 0, 105915, tzinfo=pytz.UTC),
            auto_time=dt.datetime(2019, 11, 20, 3, 1, 0, 105915, tzinfo=pytz.UTC),
        )
        # when
        mining_corporation.update_extractions_from_esi()
        # then
        self.assertEqual(refinery.extractions.count(), 2)

    def test_should_update_refinery_with_moon_from_notification_if_not_found(
        self, mock_esi
    ):
        # given
        mock_esi.client = esi_client_stub
        _, character_ownership = helpers.create_default_user_from_evecharacter(1001)
        mining_corporation = MiningCorporation.objects.create(
            eve_corporation=EveCorporationInfo.objects.get(corporation_id=2001),
            character_ownership=character_ownership,
        )
        Refinery.objects.create(
            id=1000000000001,
            moon=None,
            corporation=mining_corporation,
            eve_type=helpers.eve_type_athanor(),
        )
        # when
        mining_corporation.update_extractions_from_esi()
        # then
        obj = Refinery.objects.get(id=1000000000001)
        self.assertEqual(obj.moon, self.moon)
