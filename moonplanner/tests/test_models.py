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
    MiningCorporation,
    Moon,
    MoonProduct,
    OreRarityClass,
    Refinery,
)
from . import helpers
from .testdata.esi_client_stub import esi_client_stub
from .testdata.load_allianceauth import load_allianceauth
from .testdata.load_eveuniverse import load_eveuniverse, nearest_celestial_stub
from .testdata.survey_data import fetch_survey_data

MODELS_PATH = "moonplanner.models"
MANAGERS_PATH = "moonplanner.managers"


class TestEveOreTypeCalcRefinedValue(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()

    def test_should_return_correct_value(self):
        # given
        cinnebar = EveOreType.objects.get(id=45506)
        tungsten = EveType.objects.get(id=16637)
        mercury = EveType.objects.get(id=16646)
        evaporite_deposits = EveType.objects.get(id=16635)
        EveMarketPrice.objects.create(eve_type=tungsten, average_price=7000)
        EveMarketPrice.objects.create(eve_type=mercury, average_price=9750)
        EveMarketPrice.objects.create(eve_type=evaporite_deposits, average_price=950)
        # when
        result = cinnebar.calc_refined_value(1000000, 0.7)
        # then
        self.assertEqual(result, 400225000.0)


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


@patch(MODELS_PATH + ".MOONPLANNER_VOLUME_PER_MONTH", 1000000)
@patch(MODELS_PATH + ".MOONPLANNER_REPROCESSING_YIELD", 0.7)
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


@patch(MODELS_PATH + ".esi")
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
        MODELS_PATH + ".EveSolarSystem.nearest_celestial", new=nearest_celestial_stub
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
        self.mining_corporation.update_refineries_from_esi()
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
        self.mining_corporation.update_refineries_from_esi()
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


@patch(MODELS_PATH + ".esi")
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
        product = extraction.products.get(ore_type_id=45506)
        self.assertEqual(product.volume, 1288475.124715103)
        product = extraction.products.get(ore_type_id=46676)
        self.assertEqual(product.volume, 544691.7637724016)
        product = extraction.products.get(ore_type_id=46678)
        self.assertEqual(product.volume, 526825.4047522942)
        product = extraction.products.get(ore_type_id=46689)
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


class TestProcessSurveyInput(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()
        cls.user, cls.character_ownership = helpers.create_user_from_evecharacter(
            1001,
            permissions=[
                "moonplanner.basic_access",
                "moonplanner.extractions_access",
                "moonplanner.add_corporation",
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
        self.assertEqual(m1.products_updated_by, self.user)
        self.assertAlmostEqual(m1.products_updated_at, now(), delta=dt.timedelta(30))
        self.assertEqual(m2.products.count(), 4)
        self.assertEqual(m2.products.get(ore_type_id=45492).amount, 0.27)
        self.assertEqual(m2.products.get(ore_type_id=45494).amount, 0.23)
        self.assertEqual(m2.products.get(ore_type_id=46676).amount, 0.21)
        self.assertEqual(m2.products.get(ore_type_id=46678).amount, 0.29)


class TestMoonCalcRarityClass(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()
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
