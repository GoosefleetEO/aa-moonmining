from django.test import TestCase

from app_utils.testdata_factories import UserFactory

from .testdata.load_eveuniverse import load_eveuniverse


class TestAdminUI(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()

    def test_should_open_prices_page(self):
        # def
        user = UserFactory(is_superuser=True, is_staff=True)
        self.client.force_login(user)
        # when
        response = self.client.get("/admin/moonmining/eveoretype/")
        # then
        self.assertEqual(response.status_code, 200)
