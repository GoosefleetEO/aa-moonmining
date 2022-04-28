import datetime as dt

from django.test import TestCase
from django.utils.timezone import now

from ..core import CalculatedExtraction, CalculatedExtractionProduct


class TestCalculatedExtractionProduct(TestCase):
    def test_should_create_list(self):
        # given
        ores = {"1": 100, "2": 200}  # keys are string because they come from JSON
        # when
        lst = CalculatedExtractionProduct.create_list_from_dict(ores)
        # then
        self.assertListEqual(
            lst,
            [
                CalculatedExtractionProduct(ore_type_id=1, volume=100),
                CalculatedExtractionProduct(ore_type_id=2, volume=200),
            ],
        )

    def test_should_calculate_share(self):
        # given
        product = CalculatedExtractionProduct(ore_type_id=1, volume=400)
        # when/then
        self.assertEqual(product.calculated_share(5, 100), 0.8)


class TestCalculatedExtraction(TestCase):
    def test_should_calculate_duration(self):
        # given
        base_dt = now()
        extraction = CalculatedExtraction(
            refinery_id=1,
            status=CalculatedExtraction.Status.STARTED,
            started_at=base_dt,
            chunk_arrival_at=base_dt + dt.timedelta(days=10),
        )
        # when/then
        self.assertEqual(extraction.duration, dt.timedelta(days=10))

    def test_should_raise_exception_when_trying_to_calculate_duration_1(self):
        # given
        base_dt = now()
        extraction = CalculatedExtraction(
            refinery_id=1,
            status=CalculatedExtraction.Status.STARTED,
            started_at=base_dt,
        )
        # when/then
        with self.assertRaises(ValueError):
            extraction.duration

    def test_should_raise_exception_when_trying_to_calculate_duration_2(self):
        # given
        base_dt = now()
        extraction = CalculatedExtraction(
            refinery_id=1,
            status=CalculatedExtraction.Status.STARTED,
            chunk_arrival_at=base_dt + dt.timedelta(days=10),
        )
        # when/then
        with self.assertRaises(ValueError):
            extraction.duration

    def test_should_calculate_total_volume(self):
        # given
        extraction = CalculatedExtraction(
            refinery_id=1, status=CalculatedExtraction.Status.STARTED
        )
        ores = {"45506": 10000, "46676": 20000}
        extraction.products = CalculatedExtractionProduct.create_list_from_dict(ores)
        # when/then
        self.assertEqual(extraction.total_volume(), 30000)

    def test_should_calculate_total_volume_without_products(self):
        # given
        extraction = CalculatedExtraction(
            refinery_id=1, status=CalculatedExtraction.Status.STARTED
        )
        # when/then
        self.assertEqual(extraction.total_volume(), 0)

    def test_should_calculate_moon_products_estimate(self):
        # given
        base_time = now()
        extraction = CalculatedExtraction(
            refinery_id=1,
            status=CalculatedExtraction.Status.STARTED,
            started_at=base_time,
            chunk_arrival_at=base_time + dt.timedelta(days=20),
        )
        ores = {"45506": 7_683_200, "46676": 9_604_000}
        extraction.products = CalculatedExtractionProduct.create_list_from_dict(ores)
        # when
        products = extraction.moon_products_estimated(960_400)
        # then
        self.assertAlmostEqual(products[0].amount, 0.4, places=2)
        self.assertAlmostEqual(products[1].amount, 0.5, places=2)

    def test_should_calculate_moon_products_estimate_with_overflow(self):
        # given
        base_time = now()
        extraction = CalculatedExtraction(
            refinery_id=1,
            status=CalculatedExtraction.Status.STARTED,
            started_at=base_time,
            chunk_arrival_at=base_time + dt.timedelta(days=20),
        )
        ores = {"45506": 10_564_400, "46676": 12_677_280}
        extraction.products = CalculatedExtractionProduct.create_list_from_dict(ores)
        # when
        products = extraction.moon_products_estimated(960_400)
        # then
        self.assertAlmostEqual(products[0].amount, 0.45, places=2)
        self.assertAlmostEqual(products[1].amount, 0.55, places=2)
