from unittest.mock import Mock, patch

from app_utils.testing import create_user_from_evecharacter, json_response_to_dict

from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase
from django.urls import reverse

from esi.models import Token
from eveuniverse.models import EveMoon

from .. import views
from ..models import Moon
from . import helpers
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


class TestMoonListData(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.factory = RequestFactory()
        load_eveuniverse()
        load_allianceauth()
        cls.user, _ = create_user_from_evecharacter(
            1001,
            permissions=[
                "moonplanner.access_moonplanner",
                "moonplanner.access_our_moons",
            ],
            scopes=[
                "esi-industry.read_corporation_mining.v1",
                "esi-universe.read_structures.v1",
                "esi-characters.read_notifications.v1",
                "esi-corporations.read_structures.v1",
            ],
        )
        Moon.objects.create(eve_moon=EveMoon.objects.get(id=40131695))
        Moon.objects.create(eve_moon=EveMoon.objects.get(id=40161708))
        Moon.objects.create(eve_moon=EveMoon.objects.get(id=40161709))

    def test_should_return_all_moons(self):
        # given
        request = self.factory.get(
            reverse("moonplanner:moon_list_data", args={"category": "all_moons"})
        )
        request.user = self.user
        # when
        response = views.moon_list_data(request, category="all moons")
        # then
        self.assertEqual(response.status_code, 200)
        data = json_response_to_dict(response)
        self.assertSetEqual(set(data.keys()), {40131695, 40161708, 40161709})
        obj = data[40161708]
        self.assertEqual(obj["moon_name"], "Auga V - Moon 1")


class TestViewsAreWorking(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.factory = RequestFactory()
        load_eveuniverse()
        load_allianceauth()
        cls.user, _ = create_user_from_evecharacter(
            1001,
            permissions=[
                "moonplanner.access_moonplanner",
                "moonplanner.access_our_moons",
                "moonplanner.access_all_moons",
                "moonplanner.upload_moon_scan",
                "moonplanner.add_mining_corporation",
            ],
            scopes=[
                "esi-industry.read_corporation_mining.v1",
                "esi-universe.read_structures.v1",
                "esi-characters.read_notifications.v1",
                "esi-corporations.read_structures.v1",
            ],
        )
        helpers.create_moons()

    def test_should_open_extractions_page(self):
        # given
        request = self.factory.get(reverse("moonplanner:extractions"))
        request.user = self.user
        # when
        response = views.extractions(request)
        # then
        self.assertEqual(response.status_code, 200)

    def test_should_open_add_moon_scan_page(self):
        # given
        request = self.factory.get(reverse("moonplanner:add_moon_scan"))
        request.user = self.user
        # when
        response = views.add_moon_scan(request)
        # then
        self.assertEqual(response.status_code, 200)

    def test_should_open_all_moons_page(self):
        # given
        request = self.factory.get(reverse("moonplanner:moon_list_all"))
        request.user = self.user
        # when
        response = views.moon_list_all(request)
        # then
        self.assertEqual(response.status_code, 200)

    def test_should_open_our_moons_page(self):
        # given
        request = self.factory.get(reverse("moonplanner:moon_list_ours"))
        request.user = self.user
        # when
        response = views.moon_list_ours(request)
        # then
        self.assertEqual(response.status_code, 200)

    def test_should_open_moon_detail_page(self):
        # given
        request = self.factory.get(reverse("moonplanner:moon_info", args=["40161708"]))
        request.user = self.user
        # when
        response = views.moon_info(request, 40161708)
        # then
        self.assertEqual(response.status_code, 200)
