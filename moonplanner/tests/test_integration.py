from app_utils.testing import create_user_from_evecharacter
from django_webtest import WebTest

from django.test import override_settings
from django.urls import reverse

from .testdata.load_allianceauth import load_allianceauth
from .testdata.load_eveuniverse import load_eveuniverse

VIEWS_PATH = "moonplanner.views"


@override_settings(CELERY_ALWAYS_EAGER=True)
class TestAddMiningCorporation(WebTest):
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
        )

    def test_should_open_extractions(self):
        # given
        self.app.set_user(self.user)
        # when
        index = self.app.get(reverse("moonplanner:extractions"))
        # then
        self.assertEqual(index.status_code, 200)
