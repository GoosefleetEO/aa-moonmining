import datetime as dt
from unittest.mock import Mock, patch

from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils.timezone import now
from esi.models import Token
from eveuniverse.models import EveMoon

from allianceauth.eveonline.models import EveCorporationInfo
from app_utils.testing import create_user_from_evecharacter, json_response_to_dict

from .. import views
from ..models import Extraction, MiningCorporation, Moon, Refinery
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

    @patch(MODULE_PATH + ".update_mining_corporation")
    @patch(MODULE_PATH + ".messages_plus")
    def test_should_add_new_corporation(
        self, mock_messages, mock_update_mining_corporation
    ):
        # given
        token = Mock(spec=Token)
        token.character_id = self.character_ownership.character.character_id
        request = self.factory.get(reverse("moonplanner:add_mining_corporation"))
        request.user = self.user
        request.token = token
        middleware = SessionMiddleware()
        middleware.process_request(request)
        orig_view = views.add_mining_corporation.__wrapped__.__wrapped__.__wrapped__
        # when
        response = orig_view(request, token)
        # then
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("moonplanner:extractions"))
        self.assertTrue(mock_messages.success.called)
        self.assertTrue(mock_update_mining_corporation.delay.called)
        obj = MiningCorporation.objects.get(eve_corporation__corporation_id=2001)
        self.assertEqual(obj.character_ownership, self.character_ownership)

    @patch(MODULE_PATH + ".update_mining_corporation")
    @patch(MODULE_PATH + ".messages_plus")
    def test_should_update_existing_corporation(
        self, mock_messages, mock_update_mining_corporation
    ):
        # given
        MiningCorporation.objects.create(
            eve_corporation=EveCorporationInfo.objects.get(corporation_id=2001),
            character_ownership=None,
        )
        token = Mock(spec=Token)
        token.character_id = self.character_ownership.character.character_id
        request = self.factory.get(reverse("moonplanner:add_mining_corporation"))
        request.user = self.user
        request.token = token
        middleware = SessionMiddleware()
        middleware.process_request(request)
        orig_view = views.add_mining_corporation.__wrapped__.__wrapped__.__wrapped__
        # when
        response = orig_view(request, token)
        # then
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("moonplanner:extractions"))
        self.assertTrue(mock_messages.success.called)
        self.assertTrue(mock_update_mining_corporation.delay.called)
        obj = MiningCorporation.objects.get(eve_corporation__corporation_id=2001)
        self.assertEqual(obj.character_ownership, self.character_ownership)

    @patch(MODULE_PATH + ".update_mining_corporation")
    @patch(MODULE_PATH + ".messages_plus")
    def test_should_raise_404_if_character_ownership_not_found(
        self, mock_messages, mock_update_mining_corporation
    ):
        # given
        token = Mock(spec=Token)
        token.character_id = 1099
        request = self.factory.get(reverse("moonplanner:add_mining_corporation"))
        request.user = self.user
        request.token = token
        middleware = SessionMiddleware()
        middleware.process_request(request)
        orig_view = views.add_mining_corporation.__wrapped__.__wrapped__.__wrapped__
        # when
        response = orig_view(request, token)
        # then
        self.assertEqual(response.status_code, 404)


class TestMoonListData(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.factory = RequestFactory()
        load_eveuniverse()
        load_allianceauth()
        Moon.objects.create(eve_moon=EveMoon.objects.get(id=40131695))
        Moon.objects.create(eve_moon=EveMoon.objects.get(id=40161708))
        Moon.objects.create(eve_moon=EveMoon.objects.get(id=40161709))

    def test_should_return_all_moons(self):
        # given
        user, _ = create_user_from_evecharacter(
            1001,
            permissions=[
                "moonplanner.access_moonplanner",
                "moonplanner.access_all_moons",
            ],
            scopes=MiningCorporation.esi_scopes(),
        )
        request = self.factory.get(
            reverse("moonplanner:moon_list_data", args={"category": "all_moons"})
        )
        request.user = user
        # when
        response = views.moon_list_data(request, category="all_moons")
        # then
        self.assertEqual(response.status_code, 200)
        data = json_response_to_dict(response)
        self.assertSetEqual(set(data.keys()), {40131695, 40161708, 40161709})
        obj = data[40161708]
        self.assertEqual(obj["moon_name"], "Auga V - Moon 1")

    def test_should_return_our_moons_only(self):
        # given
        request = self.factory.get(
            reverse("moonplanner:moon_list_data", args={"category": "our_moons"})
        )
        user, _ = create_user_from_evecharacter(
            1001,
            permissions=[
                "moonplanner.access_moonplanner",
                "moonplanner.access_our_moons",
            ],
            scopes=MiningCorporation.esi_scopes(),
        )
        request.user = user
        moon = Moon.objects.get(pk=40131695)
        helpers.add_refinery(moon)
        # when
        response = views.moon_list_data(request, category="our_moons")
        # then
        self.assertEqual(response.status_code, 200)
        data = json_response_to_dict(response)
        self.assertSetEqual(set(data.keys()), {40131695})

    def test_should_handle_empty_refineries(self):
        # given
        request = self.factory.get(
            reverse("moonplanner:moon_list_data", args={"category": "our_moons"})
        )
        user, _ = create_user_from_evecharacter(
            1001,
            permissions=[
                "moonplanner.access_moonplanner",
                "moonplanner.access_our_moons",
            ],
            scopes=MiningCorporation.esi_scopes(),
        )
        request.user = user
        moon = Moon.objects.get(pk=40131695)
        refinery = helpers.add_refinery(moon)
        Refinery.objects.create(
            id=99,
            name="Empty refinery",
            corporation=refinery.corporation,
            eve_type_id=35835,
        )
        # when
        response = views.moon_list_data(request, category="our_moons")
        # then
        self.assertEqual(response.status_code, 200)
        data = json_response_to_dict(response)
        self.assertSetEqual(set(data.keys()), {40131695})

    def test_should_return_empty_list_for_all_moons(self):
        # given
        user, _ = create_user_from_evecharacter(
            1001,
            permissions=[
                "moonplanner.access_moonplanner",
                "moonplanner.access_our_moons",
            ],
            scopes=MiningCorporation.esi_scopes(),
        )
        request = self.factory.get(
            reverse("moonplanner:moon_list_data", args={"category": "all_moons"})
        )
        request.user = user
        # when
        response = views.moon_list_data(request, category="all_moons")
        # then
        self.assertEqual(response.status_code, 200)
        data = json_response_to_dict(response)
        self.assertEqual(len(data), 0)

    def test_should_return_empty_list_for_our_moons(self):
        # given
        user, _ = create_user_from_evecharacter(
            1001,
            permissions=["moonplanner.access_moonplanner"],
            scopes=MiningCorporation.esi_scopes(),
        )
        request = self.factory.get(
            reverse("moonplanner:moon_list_data", args={"category": "our_moons"})
        )
        request.user = user
        # when
        response = views.moon_list_data(request, category="our_moons")
        # then
        self.assertEqual(response.status_code, 200)
        data = json_response_to_dict(response)
        self.assertEqual(len(data), 0)


class TestMoonInfo(TestCase):
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
        moon = helpers.create_moon_40161708()
        helpers.add_refinery(moon)

    def test_should_open_page(self):
        # given
        request = self.factory.get(
            reverse("moonplanner:moon_details", args=["40161708"])
        )
        request.user = self.user
        # when
        response = views.moon_details(request, 40161708)
        # then
        self.assertEqual(response.status_code, 200)


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
        cls.moon = helpers.create_moon_40161708()
        cls.refinery = helpers.add_refinery(cls.moon)

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

    def test_should_open_moons_page(self):
        # given
        request = self.factory.get(reverse("moonplanner:moon_list"))
        request.user = self.user
        # when
        response = views.moon_list(request)
        # then
        self.assertEqual(response.status_code, 200)

    def test_should_handle_empty_refineries_extractions_page(self):
        # given
        request = self.factory.get(reverse("moonplanner:extractions"))
        request.user = self.user
        refinery = Refinery.objects.create(
            id=99,
            name="Empty refinery",
            corporation=self.refinery.corporation,
            eve_type_id=35835,
        )
        Extraction.objects.create(
            refinery=refinery,
            ready_time=now() + dt.timedelta(days=1),
            auto_time=now() + dt.timedelta(days=1),
        )
        # when
        response = views.extractions(request)
        # then
        self.assertEqual(response.status_code, 200)
