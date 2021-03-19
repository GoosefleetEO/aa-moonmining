#  from unittest.mock import patch

from app_utils.testing import NoSocketsTestCase

from eveuniverse.models import EveMarketPrice, EveType

from ..models import ExtractionProduct
from . import helpers
from .testdata.load_allianceauth import load_allianceauth
from .testdata.load_eveuniverse import load_eveuniverse

MODULE_PATH = "moonplanner.models"


class TestMoonCalcIncome(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        cls.moon = helpers.create_moon()

    def test_should_calc_income(self):
        # given
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
        # when
        result = self.moon.calc_income_estimate(
            total_volume=1000000, reprocessing_yield=0.7
        )
        # then
        self.assertIsNotNone(result)

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
        result = obj.calc_value_estimate(0.7)
        # then
        self.assertIsNotNone(result)
