from unittest.mock import Mock, patch

from app_utils.testing import create_user_from_evecharacter

from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase
from django.urls import reverse

from esi.models import Token

from .. import views
from .testdata.load_allianceauth import load_allianceauth
from .testdata.load_eveuniverse import load_eveuniverse

MODULE_PATH = "moonplanner.views"


class TestAddMinningCorporation(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        load_allianceauth()
        load_eveuniverse()
        cls.factory = RequestFactory()
        cls.user, cls.character_ownership = create_user_from_evecharacter(
            1001, permissions=["moonplanner.add_mining_corporation"]
        )
        cls.character = cls.character_ownership.character

    @patch(MODULE_PATH + ".run_refineries_update")
    @patch(MODULE_PATH + ".messages_plus")
    def test_view_add_structure_owner_normal(
        self, mock_messages, mock_run_refineries_update
    ):
        token = Mock(spec=Token)
        token.character_id = self.character.character_id
        request = self.factory.get(reverse("moonplanner:add_mining_corporation"))
        request.user = self.user
        request.token = token
        middleware = SessionMiddleware()
        middleware.process_request(request)
        orig_view = views.add_mining_corporation.__wrapped__.__wrapped__.__wrapped__
        response = orig_view(request, token)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("moonplanner:extractions"))
        self.assertTrue(mock_messages.success.called)
        self.assertTrue(mock_run_refineries_update.delay.called)
