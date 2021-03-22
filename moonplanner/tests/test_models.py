from unittest.mock import patch

from app_utils.testing import NoSocketsTestCase, create_user_from_evecharacter

from allianceauth.eveonline.models import EveCharacter, EveCorporationInfo
from eveuniverse.models import EveMarketPrice, EveMoon, EveType

from ..models import ExtractionProduct, MiningCorporation, Refinery, calc_refined_value
from . import helpers
from .testdata.esi_client_stub import esi_client_stub
from .testdata.load_allianceauth import load_allianceauth
from .testdata.load_eveuniverse import load_eveuniverse

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


class TestMoonCalcIncome(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        cls.moon = helpers.create_moon()

    def test_should_calc_income(self):
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
        result = self.moon.calc_income_estimate(
            total_volume=1000000, reprocessing_yield=0.7
        )
        # then
        self.assertEqual(result, 180498825.5)

    def test_should_return_none_if_prices_are_missing(self):
        # given
        EveMarketPrice.objects.create(
            eve_type=EveType.objects.get(id=45506), average_price=1, adjusted_price=2
        )
        # when
        result = self.moon.calc_income_estimate(
            total_volume=1000000, reprocessing_yield=0.7
        )
        # then
        self.assertIsNone(result)


class TestExtractionProduct(NoSocketsTestCase):
    def test_should_calculate_value_estimate(self):
        # given
        load_eveuniverse()
        load_allianceauth()
        moon = helpers.create_moon()
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
        result = obj.calc_value_estimate()
        # then
        self.assertIsNotNone(result)


def nearest_celestial_stub(eve_solar_system, x, y, z):
    eve_type = EveType.objects.get(id=14)
    if (x, y, z) == (55028384780, 7310316270, -163686684205):
        return eve_solar_system.NearestCelestial(
            eve_type=eve_type,
            eve_object=EveMoon.objects.get(id=40161708),  # Auga V - Moon 1
            distance=123,
        )
    elif (x, y, z) == (45028384780, 6310316270, -163686684205):
        return eve_solar_system.NearestCelestial(
            eve_type=eve_type,
            eve_object=EveMoon.objects.get(id=40161709),  # Auga V - Moon 2
            distance=123,
        )
    else:
        return None


@patch(MODULE_PATH + ".EveSolarSystem.nearest_celestial", new=nearest_celestial_stub)
@patch(MODULE_PATH + ".esi")
class TestMiningCorporationUpdateRefineries(NoSocketsTestCase):
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

    # def test_should_update_refinery_with_moon_from_notification_if_not_found(
    #     self, mock_esi, mock_nearest_celestial
    # ):
    #     # given
    #     mock_esi.client = esi_client_stub
    #     my_eve_moon = EveMoon.objects.get(id=40161708)
    #     mock_nearest_celestial.return_value = None
    #     # when
    #     self.mining_corporation.update_refineries_from_esi()
    #     # then
    #     refinery = Refinery.objects.get(id=1000000000001)
    #     self.assertEqual(refinery.name, "Auga - Paradise Alpha")
    #     self.assertEqual(refinery.moon.eve_moon, my_eve_moon)

    # TODO: test when refinery does not exist for notification
    # TODO: tests for extractions
