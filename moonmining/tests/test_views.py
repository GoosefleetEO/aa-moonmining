import datetime as dt
from unittest.mock import Mock, patch

import pytz

from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils.timezone import now
from esi.models import Token
from eveuniverse.models import EveMarketPrice, EveMoon

from allianceauth.eveonline.models import EveCorporationInfo
from app_utils.testing import (
    create_user_from_evecharacter,
    json_response_to_dict,
    json_response_to_python,
)

from .. import views
from ..models import EveOreType, Extraction, MiningLedgerRecord, Moon, Owner, Refinery
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
        middleware = SessionMiddleware(Mock())
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
        middleware = SessionMiddleware(Mock())
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
        middleware = SessionMiddleware(Mock())
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
        load_eveuniverse()
        load_allianceauth()
        cls.moon = helpers.create_moon_40161708()
        Moon.objects.create(eve_moon=EveMoon.objects.get(id=40131695))
        Moon.objects.create(eve_moon=EveMoon.objects.get(id=40161709))

    @staticmethod
    def _response_to_dict(response):
        data = helpers.json_response_to_python_2(response)
        return {int(obj[0]): obj for obj in data}

    def test_should_return_all_moons(self):
        # given
        user, _ = create_user_from_evecharacter(
            1001,
            permissions=[
                "moonmining.basic_access",
                "moonmining.extractions_access",
                "moonmining.view_all_moons",
            ],
            scopes=Owner.esi_scopes(),
        )
        self.client.force_login(user)
        # when
        response = self.client.get(f"/moonmining/moons_data/{views.MoonsCategory.ALL}")
        # then
        self.assertEqual(response.status_code, 200)
        data = self._response_to_dict(response)
        self.assertSetEqual(set(data.keys()), {40131695, 40161708, 40161709})
        obj = data[40161708]
        self.assertEqual(obj[1], "Auga V - 1")

    def test_should_return_our_moons_only(self):
        # given
        moon = Moon.objects.get(pk=40131695)
        helpers.add_refinery(moon)
        user, _ = create_user_from_evecharacter(
            1001,
            permissions=["moonmining.basic_access", "moonmining.extractions_access"],
            scopes=Owner.esi_scopes(),
        )
        self.client.force_login(user)
        # when
        response = self.client.get(f"/moonmining/moons_data/{views.MoonsCategory.OURS}")
        # then
        self.assertEqual(response.status_code, 200)
        data = self._response_to_dict(response)
        self.assertSetEqual(set(data.keys()), {40131695})

    def test_should_handle_empty_refineries(self):
        # given
        user, _ = create_user_from_evecharacter(
            1001,
            permissions=["moonmining.basic_access", "moonmining.extractions_access"],
            scopes=Owner.esi_scopes(),
        )
        self.client.force_login(user)
        moon = Moon.objects.get(pk=40131695)
        refinery = helpers.add_refinery(moon)
        Refinery.objects.create(
            id=99, name="Empty refinery", owner=refinery.owner, eve_type_id=35835
        )
        # when
        response = self.client.get(f"/moonmining/moons_data/{views.MoonsCategory.OURS}")
        # then
        self.assertEqual(response.status_code, 200)
        data = self._response_to_dict(response)
        self.assertSetEqual(set(data.keys()), {40131695})

    def test_should_return_empty_list_for_all_moons(self):
        # given
        user, _ = create_user_from_evecharacter(
            1001,
            permissions=["moonmining.basic_access", "moonmining.extractions_access"],
            scopes=Owner.esi_scopes(),
        )
        self.client.force_login(user)
        # when
        response = self.client.get(f"/moonmining/moons_data/{views.MoonsCategory.ALL}")
        # then
        self.assertEqual(response.status_code, 200)
        data = self._response_to_dict(response)
        self.assertEqual(len(data), 0)

    def test_should_return_empty_list_for_our_moons(self):
        # given
        user, _ = create_user_from_evecharacter(
            1001,
            permissions=["moonmining.basic_access"],
            scopes=Owner.esi_scopes(),
        )
        self.client.force_login(user)
        # when
        response = self.client.get(f"/moonmining/moons_data/{views.MoonsCategory.OURS}")
        # then
        self.assertEqual(response.status_code, 200)
        data = self._response_to_dict(response)
        self.assertEqual(len(data), 0)

    def test_should_return_uploaded_moons_only(self):
        # given
        user, _ = create_user_from_evecharacter(
            1001,
            permissions=["moonmining.basic_access", "moonmining.upload_moon_scan"],
            scopes=Owner.esi_scopes(),
        )
        self.client.force_login(user)
        self.moon.products_updated_by = user
        self.moon.save()
        # when
        response = self.client.get(
            f"/moonmining/moons_data/{views.MoonsCategory.UPLOADS}"
        )
        # then
        self.assertEqual(response.status_code, 200)
        data = self._response_to_dict(response)
        self.assertSetEqual(set(data.keys()), {40161708})


class TestMoonInfo(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()

    def test_should_open_page(self):
        # given
        moon = helpers.create_moon_40161708()
        helpers.add_refinery(moon)
        user, _ = create_user_from_evecharacter(
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
        self.client.force_login(user)
        # when
        response = self.client.get("/moonmining/moon/40161708")
        # then
        self.assertTemplateUsed(response, "moonmining/modals/moon_details.html")


class TestViewsAreWorking(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
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
        self.client.force_login(self.user)
        # when
        response = self.client.get("/moonmining/")
        # then
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/moonmining/extractions")

    def test_should_open_extractions_page(self):
        # given
        self.client.force_login(self.user)
        # when
        response = self.client.get("/moonmining/extractions")
        # then
        self.assertTemplateUsed(response, "moonmining/extractions.html")

    def test_should_open_moon_details_page(self):
        # given
        self.client.force_login(self.user)
        # when
        response = self.client.get(f"/moonmining/moon/{self.moon.pk}?new_page=yes")
        # then
        self.assertTemplateUsed(response, "moonmining/_generic_modal_page.html")

    def test_should_open_extraction_details_page(self):
        # given
        extraction = self.refinery.extractions.first()
        self.client.force_login(self.user)
        # when
        response = self.client.get(
            f"/moonmining/extraction/{extraction.pk}?new_page=yes"
        )
        # then
        self.assertTemplateUsed(response, "moonmining/_generic_modal_page.html")

    def test_should_open_add_moon_scan_page(self):
        # given
        self.client.force_login(self.user)
        # when
        response = self.client.get("/moonmining/upload_survey")
        # then
        self.assertTemplateUsed(response, "moonmining/modals/upload_survey.html")

    def test_should_open_moons_page(self):
        # given
        self.client.force_login(self.user)
        # when
        response = self.client.get("/moonmining/moons")
        # then
        self.assertTemplateUsed(response, "moonmining/moons.html")

    def test_should_open_reports_page(self):
        # given
        self.client.force_login(self.user)
        # when
        response = self.client.get("/moonmining/reports")
        # then
        self.assertTemplateUsed(response, "moonmining/reports.html")

    def test_should_handle_empty_refineries_extractions_page(self):
        # given
        refinery = Refinery.objects.create(
            id=99,
            name="Empty refinery",
            owner=self.refinery.owner,
            eve_type_id=35835,
        )
        Extraction.objects.create(
            refinery=refinery,
            chunk_arrival_at=now() + dt.timedelta(days=1),
            auto_fracture_at=now() + dt.timedelta(days=1),
            started_at=now() - dt.timedelta(days=3),
            status=Extraction.Status.STARTED,
        )
        self.client.force_login(self.user)
        # when
        response = self.client.get("/moonmining/extractions")
        # then
        self.assertTemplateUsed(response, "moonmining/extractions.html")


class TestExtractionsData(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()
        helpers.generate_eve_entities_from_allianceauth()
        moon = helpers.create_moon_40161708()
        cls.refinery = helpers.add_refinery(moon)
        cls.extraction = Extraction.objects.create(
            refinery=cls.refinery,
            chunk_arrival_at=dt.datetime(2019, 11, 20, 0, 1, 0, tzinfo=pytz.UTC),
            auto_fracture_at=dt.datetime(2019, 11, 20, 3, 1, 0, tzinfo=pytz.UTC),
            started_by_id=1001,
            started_at=now() - dt.timedelta(days=3),
            status=Extraction.Status.COMPLETED,
        )
        EveMarketPrice.objects.create(eve_type_id=45506, average_price=10)
        cls.user_1002, _ = create_user_from_evecharacter(1002)

    def test_should_show_extraction(self):
        # given
        MiningLedgerRecord.objects.create(
            refinery=self.refinery,
            character_id=1001,
            day=dt.date(2019, 11, 20),
            ore_type_id=45506,
            corporation_id=2001,
            quantity=100,
            user=self.user_1002,
        )
        user, _ = create_user_from_evecharacter(
            1001,
            permissions=[
                "moonmining.basic_access",
                "moonmining.extractions_access",
                "moonmining.view_moon_ledgers",
            ],
            scopes=Owner.esi_scopes(),
        )
        self.client.force_login(user)
        # when
        response = self.client.get(
            f"/moonmining/extractions_data/{views.ExtractionsCategory.PAST}",
        )
        # then
        self.assertEqual(response.status_code, 200)
        data = json_response_to_dict(response)
        self.assertSetEqual(set(data.keys()), {self.extraction.pk})
        obj = data[self.extraction.pk]
        self.assertIn("2019-Nov-20 00:01", obj["chunk_arrival_at"]["display"])
        self.assertEqual(obj["corporation_name"], "Wayne Technologies [WYN]")
        self.assertIn("modalExtractionLedger", obj["details"])

    def test_should_not_show_extraction(self):
        # given
        user, _ = create_user_from_evecharacter(
            1001,
            permissions=["moonmining.basic_access"],
            scopes=Owner.esi_scopes(),
        )
        self.client.force_login(user)
        # when
        response = self.client.get(
            f"/moonmining/extractions_data/{views.ExtractionsCategory.PAST}",
        )
        # then
        self.assertEqual(response.status_code, 302)

    def test_should_not_show_ledger_button_wo_permission(self):
        # given
        MiningLedgerRecord.objects.create(
            refinery=self.refinery,
            character_id=1001,
            day=dt.date(2019, 11, 20),
            ore_type_id=45506,
            corporation_id=2001,
            quantity=100,
            user=self.user_1002,
        )
        user, _ = create_user_from_evecharacter(
            1001,
            permissions=["moonmining.basic_access", "moonmining.extractions_access"],
            scopes=Owner.esi_scopes(),
        )
        self.client.force_login(user)
        # when
        response = self.client.get(
            f"/moonmining/extractions_data/{views.ExtractionsCategory.PAST}",
        )
        # then
        self.assertEqual(response.status_code, 200)
        data = json_response_to_dict(response)
        obj = data[self.extraction.pk]
        self.assertNotIn("modalExtractionLedger", obj["details"])

    def test_should_not_show_ledger_button_when_no_data(self):
        # given
        user, _ = create_user_from_evecharacter(
            1001,
            permissions=[
                "moonmining.basic_access",
                "moonmining.extractions_access",
                "moonmining.view_moon_ledgers",
            ],
            scopes=Owner.esi_scopes(),
        )
        self.client.force_login(user)
        # when
        response = self.client.get(
            f"/moonmining/extractions_data/{views.ExtractionsCategory.PAST}",
        )
        # then
        self.assertEqual(response.status_code, 200)
        data = json_response_to_dict(response)
        obj = data[self.extraction.pk]
        self.assertNotIn("modalExtractionLedger", obj["details"])


class TestReportsData(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()
        helpers.generate_eve_entities_from_allianceauth()
        cls.moon = helpers.create_moon_40161708()
        cls.refinery = helpers.add_refinery(cls.moon)
        cls.user, _ = create_user_from_evecharacter(
            1001,
            permissions=["moonmining.basic_access", "moonmining.reports_access"],
            scopes=Owner.esi_scopes(),
        )
        Moon.objects.create(
            eve_moon=EveMoon.objects.get(id=40131695), products_updated_by=cls.user
        )
        Moon.objects.create(
            eve_moon=EveMoon.objects.get(id=40161709), products_updated_by=cls.user
        )

    def test_should_return_owned_moon_values(self):
        # given
        self.client.force_login(self.user)
        # when
        response = self.client.get("/moonmining/report_owned_value_data")
        # then
        self.assertEqual(response.status_code, 200)
        # TODO: Test values

    def test_should_return_user_mining_data(self):
        # given
        today = dt.datetime(2021, 1, 15, 12, 0, tzinfo=pytz.UTC)
        months_1 = dt.datetime(2020, 12, 15, 12, 0, tzinfo=pytz.UTC)
        months_2 = dt.datetime(2020, 11, 15, 12, 0, tzinfo=pytz.UTC)
        months_3 = dt.datetime(2020, 10, 15, 12, 0, tzinfo=pytz.UTC)
        EveMarketPrice.objects.create(eve_type_id=45506, average_price=10)
        EveMarketPrice.objects.create(eve_type_id=45494, average_price=20)
        EveOreType.objects.update_current_prices(use_process_pricing=False)
        MiningLedgerRecord.objects.create(
            refinery=self.refinery,
            character_id=1001,
            day=today.date() - dt.timedelta(days=1),
            ore_type_id=45506,
            corporation_id=2001,
            quantity=100,
            user=self.user,
        )
        MiningLedgerRecord.objects.create(
            refinery=self.refinery,
            character_id=1001,
            day=today.date() - dt.timedelta(days=2),
            ore_type_id=45494,
            corporation_id=2001,
            quantity=200,
            user=self.user,
        )
        MiningLedgerRecord.objects.create(
            refinery=self.refinery,
            character_id=1001,
            day=months_1.date() - dt.timedelta(days=1),
            ore_type_id=45494,
            corporation_id=2001,
            quantity=200,
            user=self.user,
        )
        MiningLedgerRecord.objects.create(
            refinery=self.refinery,
            character_id=1001,
            day=months_2.date() - dt.timedelta(days=1),
            ore_type_id=45494,
            corporation_id=2001,
            quantity=500,
            user=self.user,
        )
        MiningLedgerRecord.objects.create(
            refinery=self.refinery,
            character_id=1001,
            day=months_3.date() - dt.timedelta(days=1),
            ore_type_id=45494,
            corporation_id=2001,
            quantity=600,
            user=self.user,
        )
        self.client.force_login(self.user)
        # when
        with patch(MODULE_PATH + ".now") as mock_now:
            mock_now.return_value = today
            response = self.client.get("/moonmining/report_user_mining_data")
        # then
        self.assertEqual(response.status_code, 200)
        data = json_response_to_dict(response)
        row = data[self.user.id]
        self.assertEqual(row["volume_month_0"], 100 * 10 + 200 * 10)
        self.assertEqual(row["price_month_0"], 10 * 100 + 20 * 200)
        self.assertEqual(row["volume_month_1"], 200 * 10)
        self.assertEqual(row["price_month_1"], 20 * 200)
        self.assertEqual(row["volume_month_2"], 500 * 10)
        self.assertEqual(row["price_month_2"], 20 * 500)
        self.assertEqual(row["volume_month_3"], 600 * 10)
        self.assertEqual(row["price_month_3"], 20 * 600)

    def test_should_return_user_uploads_data(self):
        # given
        self.client.force_login(self.user)
        # when
        response = self.client.get("/moonmining/report_user_uploaded_data")
        # then
        self.assertEqual(response.status_code, 200)
        user_data = [
            row
            for row in json_response_to_python(response)
            if row["name"] == "Bruce Wayne"
        ]
        self.assertEqual(user_data[0]["num_moons"], 2)

    def test_should_return_ore_prices(self):
        # given
        helpers.generate_market_prices()
        self.client.force_login(self.user)
        # when
        response = self.client.get("/moonmining/report_ore_prices_data")
        # then
        self.assertEqual(response.status_code, 200)
        data = json_response_to_dict(response)
        ore = data[45506]
        self.assertEqual(ore["name"], "Cinnabar")
        self.assertEqual(ore["price"], 2400.0)
        self.assertEqual(ore["group"], "Rare Moon Asteroids")
        self.assertEqual(ore["rarity_str"], "R32")


class TestExtractionLedgerData(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_eveuniverse()
        load_allianceauth()
        helpers.generate_eve_entities_from_allianceauth()
        moon = helpers.create_moon_40161708()
        cls.refinery = helpers.add_refinery(moon)
        cls.extraction = Extraction.objects.create(
            refinery=cls.refinery,
            chunk_arrival_at=dt.datetime(2019, 11, 20, 0, 1, 0, tzinfo=pytz.UTC),
            auto_fracture_at=dt.datetime(2019, 11, 20, 3, 1, 0, tzinfo=pytz.UTC),
            started_by_id=1001,
            started_at=now() - dt.timedelta(days=3),
            status=Extraction.Status.STARTED,
        )
        user_1001, _ = create_user_from_evecharacter(
            1001,
            permissions=[
                "moonmining.basic_access",
                "moonmining.extractions_access",
                "moonmining.view_moon_ledgers",
            ],
            scopes=Owner.esi_scopes(),
        )
        EveMarketPrice.objects.create(eve_type_id=45506, average_price=10)
        MiningLedgerRecord.objects.create(
            refinery=cls.refinery,
            character_id=1001,
            day=dt.date(2021, 4, 18),
            ore_type_id=45506,
            corporation_id=2001,
            quantity=100,
            user=user_1001,
        )

    def test_should_show_ledger(self):
        # given
        user_1002, _ = create_user_from_evecharacter(
            1002,
            permissions=[
                "moonmining.basic_access",
                "moonmining.extractions_access",
                "moonmining.view_moon_ledgers",
            ],
            scopes=Owner.esi_scopes(),
        )
        self.client.force_login(user_1002)
        # when
        response = self.client.get(
            f"/moonmining/extraction_ledger/{self.extraction.pk}",
        )
        # then
        self.assertTemplateUsed(response, "moonmining/modals/extraction_ledger.html")

    def test_should_not_show_ledger(self):
        # given
        user_1002, _ = create_user_from_evecharacter(
            1002,
            permissions=[
                "moonmining.basic_access",
                "moonmining.extractions_access",
            ],
            scopes=Owner.esi_scopes(),
        )
        self.client.force_login(user_1002)
        # when
        response = self.client.get(
            f"/moonmining/extraction_ledger/{self.extraction.pk}",
        )
        # then
        self.assertEqual(response.status_code, 302)
