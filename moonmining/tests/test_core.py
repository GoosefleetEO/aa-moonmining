from django.test import TestCase

from ..core import CalculatedExtractionProduct


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
