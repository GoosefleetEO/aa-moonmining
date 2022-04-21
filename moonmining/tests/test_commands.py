from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import override_settings
from eveuniverse.models import EveMarketPrice, EveType

from app_utils.testing import NoSocketsTestCase

from ..models import Moon
from .testdata.esi_client_stub import esi_client_stub
from .testdata.load_eveuniverse import load_eveuniverse

MODELS_PATH = "moonmining.models"
PACKAGE_PATH = "moonmining.management.commands"


@patch(MODELS_PATH + ".esi")
@override_settings(CELERY_ALWAYS_EAGER=True, CELERY_EAGER_PROPAGATES_EXCEPTIONS=True)
class TestImportMoons(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        cls.import_file = Path(__file__).parent / "testdata" / "moons_for_import.csv"

    def setUp(self) -> None:
        self.out = StringIO()

    @patch(PACKAGE_PATH + ".moonmining_import_moons.is_esi_online", new=lambda: True)
    def test_should_create_moons(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        tungsten = EveType.objects.get(id=16637)
        mercury = EveType.objects.get(id=16646)
        evaporite_deposits = EveType.objects.get(id=16635)
        EveMarketPrice.objects.create(eve_type=tungsten, average_price=7000)
        EveMarketPrice.objects.create(eve_type=mercury, average_price=9750)
        EveMarketPrice.objects.create(eve_type=evaporite_deposits, average_price=950)
        # when
        call_command("moonmining_import_moons", str(self.import_file), stdout=self.out)
        # then
        m1 = Moon.objects.get(pk=40161708)
        self.assertIsNone(m1.products_updated_by)
        self.assertIsNone(m1.products_updated_at)
        self.assertEqual(m1.products.count(), 4)
        self.assertEqual(m1.products.get(ore_type_id=45506).amount, 0.19)
        self.assertEqual(m1.products.get(ore_type_id=46676).amount, 0.23)
        self.assertEqual(m1.products.get(ore_type_id=46678).amount, 0.25)
        self.assertEqual(m1.products.get(ore_type_id=46689).amount, 0.33)

        m2 = Moon.objects.get(pk=40161709)
        self.assertIsNone(m2.products_updated_by)
        self.assertIsNone(m2.products_updated_at)
        self.assertEqual(m2.products.count(), 4)
        self.assertEqual(m2.products.get(ore_type_id=45492).amount, 0.27)
        self.assertEqual(m2.products.get(ore_type_id=45494).amount, 0.23)
        self.assertEqual(m2.products.get(ore_type_id=46676).amount, 0.21)
        self.assertEqual(m2.products.get(ore_type_id=46678).amount, 0.29)

    @patch(PACKAGE_PATH + ".moonmining_import_moons.is_esi_online", new=lambda: True)
    def test_should_abort_when_input_file_not_found(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        import_file = Path(__file__).parent / "testdata" / "unknown_file.xyz"
        # when/then
        with self.assertRaises(CommandError):
            call_command("moonmining_import_moons", str(import_file), stdout=self.out)

    @patch(PACKAGE_PATH + ".moonmining_import_moons.is_esi_online", new=lambda: False)
    def test_should_abort_when_esi_is_offline(self, mock_esi):
        # given
        mock_esi.client = esi_client_stub
        # when/then
        with self.assertRaises(CommandError):
            call_command(
                "moonmining_import_moons", str(self.import_file), stdout=self.out
            )
