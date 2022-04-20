from django.test import TestCase

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


class TestCalculatedExtraction(TestCase):
    def test_should_calculate_total_volume(self):
        # given
        extraction = CalculatedExtraction(
            refinery_id=1, status=CalculatedExtraction.Status.STARTED
        )
        ores = {"45506": 10000, "46676": 20000}
        extraction.products = CalculatedExtractionProduct.create_list_from_dict(ores)
        # when/then
        self.assertEqual(extraction.total_volume(), 30000)
