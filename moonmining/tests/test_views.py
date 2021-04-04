import datetime as dt
from unittest.mock import Mock, patch

import pytz

from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils.timezone import now
from esi.models import Token
from eveuniverse.models import EveMoon

from allianceauth.eveonline.models import EveCorporationInfo
from app_utils.testing import create_user_from_evecharacter, json_response_to_dict

from .. import views
from ..models import Extraction, Moon, Owner, Refinery
from . import helpers
from .testdata.load_allianceauth import load_allianceauth
from .testdata.load_eveuniverse import load_eveuniverse

MODULE_PATH = "moonmining.views"


class TestOwner(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        load_allianceauth()
        load_eveuniverse()
        cls.factory = RequestFactory()
        cls.user, cls.character_ownership = create_user_from_evecharacter(
            1001, permissions=["moonmining.add_refinery_owner"]
        )

    @patch(MODULE_PATH + ".notify_admins")
    @patch(MODULE_PATH + ".tasks.update_owner")
    @patch(MODULE_PATH + ".messages_plus")
    def test_should_add_new_owner(
        self, mock_messages, mock_update_owner, mock_notify_admins
    ):
        # given
        token = Mock(spec=Token)
        token.character_id = self.character_ownership.character.character_id
        request = self.factory.get(reverse("moonmining:add_owner"))
        request.user = self.user
        request.token = token
        middleware = SessionMiddleware()
        middleware.process_request(request)
        orig_view = views.add_owner.__wrapped__.__wrapped__.__wrapped__
        # when
        response = orig_view(request, token)
        # then
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("moonmining:index"))
        self.assertTrue(mock_messages.success.called)
        self.assertTrue(mock_update_owner.delay.called)
        self.assertTrue(mock_notify_admins.called)
        obj = Owner.objects.get(corporation__corporation_id=2001)
        self.assertEqual(obj.character_ownership, self.character_ownership)

    @patch(MODULE_PATH + ".tasks.update_owner")
    @patch(MODULE_PATH + ".messages_plus")
    def test_should_update_existing_owner(self, mock_messages, mock_update_owner):
        # given
        Owner.objects.create(
            corporation=EveCorporationInfo.objects.get(corporation_id=2001),
            character_ownership=None,
        )
        token = Mock(spec=Token)
        token.character_id = self.character_ownership.character.character_id
        request = self.factory.get(reverse("moonmining:add_owner"))
        request.user = self.user
        request.token = token
        middleware = SessionMiddleware()
        middleware.process_request(request)
        orig_view = views.add_owner.__wrapped__.__wrapped__.__wrapped__
        # when
        response = orig_view(request, token)
        # then
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("moonmining:index"))
        self.assertTrue(mock_messages.success.called)
        self.assertTrue(mock_update_owner.delay.called)
        obj = Owner.objects.get(corporation__corporation_id=2001)
        self.assertEqual(obj.character_ownership, self.character_ownership)

    @patch(MODULE_PATH + ".tasks.update_owner")
    @patch(MODULE_PATH + ".messages_plus")
    def test_should_raise_404_if_character_ownership_not_found(
        self, mock_messages, mock_update_owner
    ):
        # given
        token = Mock(spec=Token)
        token.character_id = 1099
        request = self.factory.get(reverse("moonmining:add_owner"))
        request.user = self.user
        request.token = token
        middleware = SessionMiddleware()
        middleware.process_request(request)
        orig_view = views.add_owner.__wrapped__.__wrapped__.__wrapped__
        # when
        response = orig_view(request, token)
        # then
        self.assertEqual(response.status_code, 404)


class TestMoonsData(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.factory = RequestFactory()
        load_eveuniverse()
        load_allianceauth()
        cls.moon = helpers.create_moon_40161708()
        Moon.objects.create(eve_moon=EveMoon.objects.get(id=40131695))
        Moon.objects.create(eve_moon=EveMoon.objects.get(id=40161709))

    def test_should_return_all_moons(self):
        # given
        user, _ = create_user_from_evecharacter(
            1001,
            permissions=["moonmining.basic_access", "moonmining.view_all_moons"],
            scopes=Owner.esi_scopes(),
        )
        request = self.factory.get(
            reverse("moonmining:moons_data", args={"category": views.MoonsCategory.ALL})
        )
        request.user = user
        # when
        response = views.moons_data(request, category=views.MoonsCategory.ALL)
        # then
        self.assertEqual(response.status_code, 200)
        data = json_response_to_dict(response)
        self.assertSetEqual(set(data.keys()), {40131695, 40161708, 40161709})
        obj = data[40161708]
        self.assertEqual(obj["moon_name"], "Auga V - Moon 1")

    def test_should_return_our_moons_only(self):
        # given
        request = self.factory.get(
            reverse(
                "moonmining:moons_data", args={"category": views.MoonsCategory.OURS}
            )
        )
        user, _ = create_user_from_evecharacter(
            1001,
            permissions=["moonmining.basic_access", "moonmining.extractions_access"],
            scopes=Owner.esi_scopes(),
        )
        request.user = user
        moon = Moon.objects.get(pk=40131695)
        helpers.add_refinery(moon)
        # when
        response = views.moons_data(request, category=views.MoonsCategory.OURS)
        # then
        self.assertEqual(response.status_code, 200)
        data = json_response_to_dict(response)
        self.assertSetEqual(set(data.keys()), {40131695})

    def test_should_handle_empty_refineries(self):
        # given
        request = self.factory.get(
            reverse(
                "moonmining:moons_data", args={"category": views.MoonsCategory.OURS}
            )
        )
        user, _ = create_user_from_evecharacter(
            1001,
            permissions=["moonmining.basic_access", "moonmining.extractions_access"],
            scopes=Owner.esi_scopes(),
        )
        request.user = user
        moon = Moon.objects.get(pk=40131695)
        refinery = helpers.add_refinery(moon)
        Refinery.objects.create(
            id=99, name="Empty refinery", owner=refinery.owner, eve_type_id=35835
        )
        # when
        response = views.moons_data(request, category=views.MoonsCategory.OURS)
        # then
        self.assertEqual(response.status_code, 200)
        data = json_response_to_dict(response)
        self.assertSetEqual(set(data.keys()), {40131695})

    def test_should_return_empty_list_for_all_moons(self):
        # given
        user, _ = create_user_from_evecharacter(
            1001,
            permissions=["moonmining.basic_access", "moonmining.extractions_access"],
            scopes=Owner.esi_scopes(),
        )
        request = self.factory.get(
            reverse("moonmining:moons_data", args={"category": views.MoonsCategory.ALL})
        )
        request.user = user
        # when
        response = views.moons_data(request, category=views.MoonsCategory.ALL)
        # then
        self.assertEqual(response.status_code, 200)
        data = json_response_to_dict(response)
        self.assertEqual(len(data), 0)

    def test_should_return_empty_list_for_our_moons(self):
        # given
        user, _ = create_user_from_evecharacter(
            1001,
            permissions=["moonmining.basic_access"],
            scopes=Owner.esi_scopes(),
        )
        request = self.factory.get(
            reverse(
                "moonmining:moons_data", args={"category": views.MoonsCategory.OURS}
            )
        )
        request.user = user
        # when
        response = views.moons_data(request, category=views.MoonsCategory.OURS)
        # then
        self.assertEqual(response.status_code, 200)
        data = json_response_to_dict(response)
        self.assertEqual(len(data), 0)

    def test_should_return_uploaded_moons_only(self):
        # given
        request = self.factory.get(
            reverse(
                "moonmining:moons_data",
                args={"category": views.MoonsCategory.UPLOADS},
            )
        )
        user, _ = create_user_from_evecharacter(
            1001,
            permissions=["moonmining.basic_access", "moonmining.upload_moon_scan"],
            scopes=Owner.esi_scopes(),
        )
        request.user = user
        self.moon.products_updated_by = user
        self.moon.save()
        # when
        response = views.moons_data(request, category=views.MoonsCategory.UPLOADS)
        # then
        self.assertEqual(response.status_code, 200)
        data = json_response_to_dict(response)
        self.assertSetEqual(set(data.keys()), {40161708})


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
                "moonmining.basic_access",
                "moonmining.extractions_access",
                "moonmining.view_all_moons",
                "moonmining.upload_moon_scan",
                "moonmining.add_refinery_owner",
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
            reverse("moonmining:moon_details", args=["40161708"])
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
                "moonmining.basic_access",
                "moonmining.extractions_access",
                "moonmining.reports_access",
                "moonmining.view_all_moons",
                "moonmining.upload_moon_scan",
                "moonmining.add_refinery_owner",
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

    def test_should_redirect_to_extractions_page(self):
        # given
        request = self.factory.get(reverse("moonmining:index"))
        request.user = self.user
        # when
        response = views.index(request)
        # then
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("moonmining:extractions"))

    def test_should_open_extractions_page(self):
        # given
        request = self.factory.get(reverse("moonmining:extractions"))
        request.user = self.user
        # when
        response = views.extractions(request)
        # then
        self.assertEqual(response.status_code, 200)

    def test_should_open_moon_details_page(self):
        # given
        request = self.factory.get(
            path=reverse("moonmining:moon_details", args=[self.moon.pk]),
            data={"new_page": "yes"},
        )
        request.user = self.user
        # when
        response = views.moon_details(request, self.moon.pk)
        # then
        self.assertEqual(response.status_code, 200)

    def test_should_open_extraction_details_page(self):
        # given
        extraction = self.refinery.extractions.first()
        request = self.factory.get(
            path=reverse("moonmining:extraction_details", args=[extraction.pk]),
            data={"new_page": "yes"},
        )
        request.user = self.user
        # when
        response = views.extraction_details(request, extraction.pk)
        # then
        self.assertEqual(response.status_code, 200)

    def test_should_open_add_moon_scan_page(self):
        # given
        request = self.factory.get(reverse("moonmining:upload_survey"))
        request.user = self.user
        # when
        response = views.upload_survey(request)
        # then
        self.assertEqual(response.status_code, 200)

    def test_should_open_moons_page(self):
        # given
        request = self.factory.get(reverse("moonmining:moons"))
        request.user = self.user
        # when
        response = views.moons(request)
        # then
        self.assertEqual(response.status_code, 200)

    def test_should_open_reports_page(self):
        # given
        request = self.factory.get(reverse("moonmining:reports"))
        request.user = self.user
        # when
        response = views.reports(request)
        # then
        self.assertEqual(response.status_code, 200)

    def test_should_handle_empty_refineries_extractions_page(self):
        # given
        request = self.factory.get(reverse("moonmining:extractions"))
        request.user = self.user
        refinery = Refinery.objects.create(
            id=99,
            name="Empty refinery",
            owner=self.refinery.owner,
            eve_type_id=35835,
        )
        Extraction.objects.create(
            refinery=refinery,
            ready_time=now() + dt.timedelta(days=1),
            auto_time=now() + dt.timedelta(days=1),
            started_at=now() - dt.timedelta(days=3),
            status=Extraction.Status.STARTED,
        )
        # when
        response = views.extractions(request)
        # then
        self.assertEqual(response.status_code, 200)


class TestExtractionsData(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.factory = RequestFactory()
        load_eveuniverse()
        load_allianceauth()
        helpers.generate_eve_entities_from_allianceauth()
        moon = helpers.create_moon_40161708()
        cls.refinery = helpers.add_refinery(moon)

    def test_should_return_all_moons(self):
        # given
        user, _ = create_user_from_evecharacter(
            1001,
            permissions=["moonmining.basic_access", "moonmining.extractions_access"],
            scopes=Owner.esi_scopes(),
        )
        extraction = Extraction.objects.create(
            refinery=self.refinery,
            ready_time=dt.datetime(2019, 11, 20, 0, 1, 0, tzinfo=pytz.UTC),
            auto_time=dt.datetime(2019, 11, 20, 3, 1, 0, tzinfo=pytz.UTC),
            started_by_id=1001,
            started_at=now() - dt.timedelta(days=3),
            status=Extraction.Status.STARTED,
        )
        request = self.factory.get(
            reverse(
                "moonmining:extractions_data",
                args={"category": views.ExtractionsCategory.PAST},
            )
        )
        request.user = user
        # when
        response = views.extractions_data(
            request, category=views.ExtractionsCategory.PAST
        )
        # then
        self.assertEqual(response.status_code, 200)
        data = json_response_to_dict(response)
        self.assertSetEqual(set(data.keys()), {extraction.pk})
        obj = data[extraction.pk]
        self.assertIn("2019-Nov-20 00:01", obj["ready_time"]["display"])
        self.assertEqual(obj["corporation_name"], "Wayne Technologies [WYN]")


class TestReportsData(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.factory = RequestFactory()
        load_eveuniverse()
        load_allianceauth()
        cls.moon = helpers.create_moon_40161708()
        Moon.objects.create(eve_moon=EveMoon.objects.get(id=40131695))
        Moon.objects.create(eve_moon=EveMoon.objects.get(id=40161709))

    def test_should_return_owned_moon_values(self):
        # given
        user, _ = create_user_from_evecharacter(
            1001,
            permissions=["moonmining.basic_access", "moonmining.reports_access"],
            scopes=Owner.esi_scopes(),
        )
        request = self.factory.get(reverse("moonmining:report_owned_value_data"))
        request.user = user
        # when
        response = views.report_owned_value_data(request)
        # then
        self.assertEqual(response.status_code, 200)
        # TODO: Test values
