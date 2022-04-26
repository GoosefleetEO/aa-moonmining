import datetime as dt
from collections import defaultdict
from enum import Enum

from django_datatables_view.base_datatable_view import BaseDatatableView

from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth.models import User
from django.db import models
from django.db.models import (
    Case,
    Count,
    ExpressionWrapper,
    F,
    FloatField,
    IntegerField,
    Min,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce, Concat
from django.http import HttpResponseNotFound, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.html import format_html, strip_tags
from django.utils.timezone import now
from django.views.decorators.cache import cache_page
from esi.decorators import token_required

from allianceauth.authentication.models import CharacterOwnership
from allianceauth.eveonline.evelinks import dotlan
from allianceauth.eveonline.models import EveCorporationInfo
from allianceauth.services.hooks import get_extension_logger
from app_utils.allianceauth import notify_admins
from app_utils.logging import LoggerAddTag
from app_utils.messages import messages_plus
from app_utils.views import fontawesome_modal_button_html, link_html, yesno_str

from . import __title__, helpers, tasks
from .app_settings import (
    MOONMINING_ADMIN_NOTIFICATIONS_ENABLED,
    MOONMINING_COMPLETED_EXTRACTIONS_HOURS_UNTIL_STALE,
    MOONMINING_REPROCESSING_YIELD,
    MOONMINING_USE_REPROCESS_PRICING,
    MOONMINING_VOLUME_PER_MONTH,
)
from .constants import DATE_FORMAT, DATETIME_FORMAT, EveGroupId
from .forms import MoonScanForm
from .helpers import HttpResponseUnauthorized
from .models import EveOreType, Extraction, Moon, Owner, Refinery

logger = LoggerAddTag(get_extension_logger(__name__), __title__)


class ExtractionsCategory(str, helpers.EnumToDict, Enum):
    UPCOMING = "upcoming"
    PAST = "past"


class MoonsCategory(str, helpers.EnumToDict, Enum):
    ALL = "all_moons"
    UPLOADS = "uploads"
    OURS = "our_moons"


def moon_link_html(moon: Moon) -> str:
    return format_html(
        '<a href="#" data-toggle="modal" '
        'data-target="#modalMoonDetails" '
        'title="Show details for this moon." '
        "data-ajax_url={}>"
        "{}</a>",
        reverse("moonmining:moon_details", args=[moon.pk]),
        moon.name,
    )


def extraction_ledger_button_html(extraction: Extraction) -> str:
    return fontawesome_modal_button_html(
        modal_id="modalExtractionLedger",
        fa_code="fas fa-table",
        ajax_url=reverse("moonmining:extraction_ledger", args=[extraction.pk]),
        tooltip="Extraction ledger",
    )


def moon_details_button_html(moon: Moon) -> str:
    return fontawesome_modal_button_html(
        modal_id="modalMoonDetails",
        fa_code="fas fa-moon",
        ajax_url=reverse("moonmining:moon_details", args=[moon.pk]),
        tooltip="Moon details",
    )


def extraction_details_button_html(extraction_pk: int) -> str:
    return fontawesome_modal_button_html(
        modal_id="modalExtractionDetails",
        fa_code="fas fa-hammer",
        ajax_url=reverse("moonmining:extraction_details", args=[extraction_pk]),
        tooltip="Extraction details",
    )


def default_if_none(value, default):
    """Return given default if value is None"""
    if value is None:
        return default
    return value


def default_if_false(value, default):
    """Return given default if value is False"""
    if not value:
        return default
    return value


@login_required
@permission_required("moonmining.basic_access")
def index(request):
    if request.user.has_perm("moonmining.extractions_access"):
        return redirect("moonmining:extractions")
    return redirect("moonmining:moons")


@login_required
@permission_required(["moonmining.extractions_access", "moonmining.basic_access"])
def extractions(request):
    context = {
        "page_title": "Extractions",
        "ExtractionsCategory": ExtractionsCategory.to_dict(),
        "ExtractionsStatus": Extraction.Status,
        "use_reprocess_pricing": MOONMINING_USE_REPROCESS_PRICING,
        "reprocessing_yield": MOONMINING_REPROCESSING_YIELD * 100,
        "total_volume_per_month": MOONMINING_VOLUME_PER_MONTH / 1000000,
        "stale_hours": MOONMINING_COMPLETED_EXTRACTIONS_HOURS_UNTIL_STALE,
    }
    return render(request, "moonmining/extractions.html", context)


@login_required
@permission_required(["moonmining.extractions_access", "moonmining.basic_access"])
def extractions_data(request, category):
    data = list()
    cutover_dt = now() - dt.timedelta(
        hours=MOONMINING_COMPLETED_EXTRACTIONS_HOURS_UNTIL_STALE
    )
    extractions = (
        Extraction.objects.annotate_volume()
        .selected_related_defaults()
        .select_related(
            "refinery__moon__eve_moon__eve_planet__eve_solar_system",
            "refinery__moon__eve_moon__eve_planet__eve_solar_system__eve_constellation",
            "refinery__moon__eve_moon__eve_planet__eve_solar_system__eve_constellation__eve_region",
        )
    )
    if category == ExtractionsCategory.UPCOMING:
        extractions = extractions.filter(auto_fracture_at__gte=cutover_dt).exclude(
            status=Extraction.Status.CANCELED
        )
    elif category == ExtractionsCategory.PAST:
        extractions = extractions.filter(
            auto_fracture_at__lt=cutover_dt
        ) | extractions.filter(status=Extraction.Status.CANCELED)
    else:
        extractions = Extraction.objects.none()
    can_see_ledger = request.user.has_perm("moonmining.view_moon_ledgers")
    for extraction in extractions:
        corporation_name = extraction.refinery.owner.name
        alliance_name = extraction.refinery.owner.alliance_name
        moon = extraction.refinery.moon
        moon_name = str(moon)
        refinery_name = str(extraction.refinery.name)
        solar_system = moon.eve_moon.eve_planet.eve_solar_system
        constellation = region = solar_system.eve_constellation
        region = constellation.eve_region
        location = format_html(
            "{}<br><i>{}</i>",
            link_html(dotlan.solar_system_url(solar_system.name), moon_name),
            region.name,
        )
        if (
            extraction.status == Extraction.Status.COMPLETED
            and extraction.ledger.exists()
        ):
            mined_value = extraction.ledger.aggregate(Sum(F("total_price")))[
                "total_price__sum"
            ]
            actions_html = (
                extraction_ledger_button_html(extraction) + "&nbsp;"
                if can_see_ledger
                else ""
            )
        else:
            actions_html = ""
            mined_value = None
        actions_html += extraction_details_button_html(extraction.pk)
        actions_html += "&nbsp;" + moon_details_button_html(extraction.refinery.moon)
        status_html = format_html(
            "{}<br>{}",
            extraction.chunk_arrival_at.strftime(DATETIME_FORMAT),
            extraction.status_enum.bootstrap_tag_html,
        )
        data.append(
            {
                "id": extraction.pk,
                "chunk_arrival_at": {
                    "display": status_html,
                    "sort": extraction.chunk_arrival_at,
                },
                "refinery": {
                    "display": extraction.refinery.name_html(),
                    "sort": refinery_name,
                },
                "location": {
                    "display": location,
                    "sort": moon_name,
                },
                "labels": moon.labels_html(),
                "volume": extraction.volume,
                "value": extraction.value if extraction.value else None,
                "mined_value": mined_value,
                "details": actions_html,
                "corporation_name": corporation_name,
                "alliance_name": alliance_name,
                "moon_name": moon_name,
                "region_name": region.name,
                "constellation_name": constellation.name,
                "rarity_class": moon.get_rarity_class_display(),
                "is_jackpot_str": yesno_str(extraction.is_jackpot),
                "is_ready": extraction.chunk_arrival_at <= now(),
                "status": extraction.status,
                "status_str": Extraction.Status(extraction.status).label,
            }
        )
    return JsonResponse(data, safe=False)


@login_required
@permission_required(["moonmining.extractions_access", "moonmining.basic_access"])
def extraction_details(request, extraction_pk: int):
    try:
        extraction = (
            Extraction.objects.annotate_volume()
            .select_related(
                "refinery",
                "refinery__moon",
                "refinery__moon__eve_moon",
                "refinery__moon__eve_moon__eve_planet__eve_solar_system",
                "refinery__moon__eve_moon__eve_planet__eve_solar_system__eve_constellation__eve_region",
                "canceled_by",
                "fractured_by",
                "started_by",
            )
            .get(pk=extraction_pk)
        )
    except Extraction.DoesNotExist:
        return HttpResponseNotFound()
    context = {
        "page_title": (
            f"{extraction.refinery.moon} "
            f"| {extraction.chunk_arrival_at.strftime(DATE_FORMAT)}"
        ),
        "extraction": extraction,
    }
    if request.GET.get("new_page"):
        context["title"] = "Extraction"
        context["content_file"] = "moonmining/partials/extraction_details.html"
        return render(request, "moonmining/_generic_modal_page.html", context)
    else:
        return render(request, "moonmining/modals/extraction_details.html", context)


@login_required
@permission_required(
    [
        "moonmining.extractions_access",
        "moonmining.basic_access",
        "moonmining.view_moon_ledgers",
    ]
)
def extraction_ledger(request, extraction_pk: int):
    try:
        extraction = (
            Extraction.objects.all()
            .select_related(
                "refinery",
                "refinery__moon",
                "refinery__moon__eve_moon__eve_planet__eve_solar_system",
                "refinery__moon__eve_moon__eve_planet__eve_solar_system__eve_constellation__eve_region",
            )
            .get(pk=extraction_pk)
        )
    except Extraction.DoesNotExist:
        return HttpResponseNotFound()
    ledger = extraction.ledger.select_related(
        "character", "corporation", "user__profile__main_character", "ore_type"
    )
    total_value = ledger.aggregate(Sum(F("total_price")))["total_price__sum"]
    total_volume = ledger.aggregate(Sum(F("total_volume")))["total_volume__sum"]
    sum_price = ExpressionWrapper(
        F("quantity") * Coalesce(F("unit_price"), 0), output_field=FloatField()
    )
    sum_volume = ExpressionWrapper(
        F("quantity") * F("ore_type__volume"), output_field=IntegerField()
    )
    character_totals = (
        ledger.values(
            character_name=F("character__name"),
            main_name=F("user__profile__main_character__character_name"),
            corporation_name=F("user__profile__main_character__corporation_name"),
        )
        .annotate(character_total_price=Sum(sum_price, distinct=True))
        .annotate(character_total_volume=Sum(sum_volume, distinct=True))
        .annotate(
            character_percent_value=ExpressionWrapper(
                F("character_total_price") / Value(total_value) * Value(100),
                output_field=IntegerField(),
            )
        )
        .annotate(
            character_percent_volume=F("character_total_volume")
            / Value(total_volume)
            * Value(100)
        )
    )
    context = {
        "page_title": (
            f"{extraction.refinery.moon} "
            f"| {extraction.chunk_arrival_at.strftime(DATE_FORMAT)}"
        ),
        "extraction": extraction,
        "total_value": total_value,
        "total_volume": total_volume,
        "ledger": ledger,
        "character_totals": character_totals,
    }
    if request.GET.get("new_page"):
        context["title"] = "Extraction Ledger"
        context["content_file"] = "moonmining/partials/extraction_ledger.html"
        return render(request, "moonmining/_generic_modal_page.html", context)
    return render(request, "moonmining/modals/extraction_ledger.html", context)


@login_required()
@permission_required("moonmining.basic_access")
def moons(request):
    context = {
        "page_title": "Moons",
        "MoonsCategory": MoonsCategory.to_dict(),
        "use_reprocess_pricing": MOONMINING_USE_REPROCESS_PRICING,
        "reprocessing_yield": MOONMINING_REPROCESSING_YIELD * 100,
        "total_volume_per_month": MOONMINING_VOLUME_PER_MONTH / 1000000,
    }
    return render(request, "moonmining/moons.html", context)


class MoonListJson(PermissionRequiredMixin, LoginRequiredMixin, BaseDatatableView):
    model = Moon
    permission_required = "moonmining.basic_access"
    columns = [
        "id",
        "moon_name",
        "rarity_class_str",
        "refinery",
        "labels",
        "solar_system_link",
        "location_html",
        "region_name",
        "constellation_name",
        "value",
        "details",
        "has_refinery_str",
        "has_extraction_str",
        "solar_system_name",
        "corporation_name",
        "alliance_name",
        "has_refinery",
        "label_name",
    ]

    # define column names that will be used in sorting
    # order is important and should be same as order of columns
    # displayed by datatables. For non sortable columns use empty
    # value like ''
    order_columns = [
        "pk",
        "name",
        "refinery__eve_solar_system__name",
        "refinery__name",
        "",
        "value",
        "",
        # hidden columns below
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
    ]

    def get_initial_queryset(self) -> models.QuerySet:
        return self.initial_queryset(
            category=self.kwargs["category"], user=self.request.user
        )

    @classmethod
    def initial_queryset(cls, category: str, user: User) -> models.QuerySet:
        current_extraction_qs = Extraction.objects.filter(
            refinery__moon=OuterRef("pk"),
            status__in=[Extraction.Status.STARTED, Extraction.Status.READY],
        )
        moon_query = (
            Moon.objects.selected_related_defaults()
            .annotate(extraction_pk=Subquery(current_extraction_qs.values("pk")[:1]))
            .annotate(
                has_refinery=Case(
                    When(refinery__isnull=True, then=Value(False)), default=Value(True)
                )
            )
            .annotate(
                has_refinery_str=Case(
                    When(has_refinery=False, then=Value("no")), default=Value("yes")
                )
            )
            .annotate(
                has_extraction=Case(
                    When(extraction_pk__isnull=True, then=Value(False)),
                    default=Value(True),
                )
            )
            .annotate(
                has_extraction_str=Case(
                    When(has_extraction=False, then=Value("no")), default=Value("yes")
                )
            )
            .annotate(
                rarity_class_str=Concat(
                    Value("R"), F("rarity_class"), output_field=models.CharField()
                )
            )
        )
        if (
            category == MoonsCategory.ALL
            and user.has_perm("moonmining.extractions_access")
            and user.has_perm("moonmining.view_all_moons")
        ):
            pass
        elif category == MoonsCategory.OURS and user.has_perm(
            "moonmining.extractions_access"
        ):
            moon_query = moon_query.filter(refinery__isnull=False)
        elif category == MoonsCategory.UPLOADS and user.has_perm(
            "moonmining.upload_moon_scan"
        ):
            moon_query = moon_query.filter(products_updated_by=user)
        else:
            moon_query = Moon.objects.none()
        return moon_query

    def filter_queryset(self, qs) -> models.QuerySet:
        """use parameters passed in GET request to filter queryset"""

        qs = self._apply_search_filter(
            qs, 7, "eve_moon__eve_planet__eve_solar_system__name"
        )
        qs = self._apply_search_filter(qs, 8, "has_refinery_str")
        qs = self._apply_search_filter(
            qs, 9, "refinery__owner__corporation__corporation_name"
        )
        qs = self._apply_search_filter(
            qs, 10, "refinery__owner__corporation__alliance__alliance_name"
        )
        qs = self._apply_search_filter(qs, 11, "rarity_class_str")
        qs = self._apply_search_filter(qs, 12, "has_extraction_str")
        qs = self._apply_search_filter(
            qs, 13, "eve_moon__eve_planet__eve_solar_system__eve_constellation__name"
        )
        qs = self._apply_search_filter(qs, 14, "label__name")
        qs = self._apply_search_filter(
            qs,
            15,
            "eve_moon__eve_planet__eve_solar_system__eve_constellation__eve_region__name",
        )

        search = self.request.GET.get("search[value]", None)
        if search:
            qs = qs.filter(
                Q(eve_moon__name__istartswith=search)
                | Q(refinery__name__istartswith=search)
            )
        return qs

        qs = self._apply_search_filter(qs, 4, "user__profile__state__name")
        qs = self._apply_search_filter(qs, 6, "character__alliance_name")
        qs = self._apply_search_filter(qs, 7, "character__corporation_name")
        qs = self._apply_search_filter(
            qs, 8, "user__profile__main_character__alliance_name"
        )
        qs = self._apply_search_filter(
            qs, 9, "user__profile__main_character__corporation_name"
        )
        qs = self._apply_search_filter(
            qs, 10, "user__profile__main_character__character_name"
        )
        qs = self._apply_search_filter(qs, 11, "unregistered")

        return qs

    def _apply_search_filter(self, qs, column_num, field) -> models.QuerySet:
        my_filter = self.request.GET.get(f"columns[{column_num}][search][value]", None)
        if my_filter:
            if self.request.GET.get(f"columns[{column_num}][search][regex]", False):
                kwargs = {f"{field}__iregex": my_filter}
            else:
                kwargs = {f"{field}__istartswith": my_filter}
            return qs.filter(**kwargs)
        return qs

    def render_column(self, row, column) -> str:
        if column == "id":
            return row.pk
        if column == "moon_name":
            return row.name
        result = self._render_location(row, column)
        if result:
            return result
        if column == "labels":
            return row.labels_html()
        if column == "label_name":
            return row.label.name if row.label else ""
        if column == "details":
            return self._render_details(row)
        result = self._render_refinery(row, column)
        if result:
            return result
        return super().render_column(row, column)

    def _render_location(self, row, column):
        solar_system = row.eve_moon.eve_planet.eve_solar_system
        if solar_system.is_high_sec:
            sec_class = "text-high-sec"
        elif solar_system.is_low_sec:
            sec_class = "text-low-sec"
        else:
            sec_class = "text-null-sec"
        solar_system_link = format_html(
            '{}&nbsp;<span class="{}">{}</span>',
            link_html(dotlan.solar_system_url(solar_system.name), solar_system.name),
            sec_class,
            round(solar_system.security_status, 1),
        )
        constellation = row.eve_moon.eve_planet.eve_solar_system.eve_constellation
        region = constellation.eve_region
        location_html = format_html(
            "{}<br><em>{}</em>", constellation.name, region.name
        )
        if column == "solar_system_name":
            return solar_system.name
        if column == "solar_system_link":
            return solar_system_link
        if column == "location_html":
            return location_html
        if column == "region_name":
            return region.name
        if column == "constellation_name":
            return constellation.name
        return None

    def _render_details(self, row):
        has_details_access = self.request.user.has_perm(
            "moonmining.extractions_access"
        ) or self.request.user.has_perm("moonmining.view_all_moons")
        if has_details_access:
            details_html = (
                extraction_details_button_html(row.extraction_pk) + " "
                if row.extraction_pk
                else ""
            )
            details_html += moon_details_button_html(row)
            return details_html
        return ""

    def _render_refinery(self, row, column):
        if row.has_refinery:
            refinery = row.refinery
            refinery_html = refinery.name_html()
            refinery_name = refinery.name
            corporation_name = refinery.owner.name
            alliance_name = refinery.owner.alliance_name
        else:
            refinery_html = "?"
            refinery_name = ""
            corporation_name = alliance_name = ""
        if column == "corporation_name":
            return corporation_name
        if column == "alliance_name":
            return alliance_name
        if column == "refinery":
            return {"display": refinery_html, "sort": refinery_name}
        return None


@login_required
@permission_required("moonmining.basic_access")
def moons_fdd_data(request, category) -> JsonResponse:
    """Provide lists for drop down fields."""
    qs = MoonListJson.initial_queryset(category=category, user=request.user)
    columns = request.GET.get("columns")
    result = dict()
    if columns:
        for column in columns.split(","):
            if column == "alliance_name":
                options = qs.exclude(
                    refinery__owner__corporation__alliance__isnull=True,
                ).values_list(
                    "refinery__owner__corporation__alliance__alliance_name", flat=True
                )
            elif column == "corporation_name":
                options = qs.exclude(refinery__isnull=True).values_list(
                    "refinery__owner__corporation__corporation_name", flat=True
                )
            elif column == "region_name":
                options = qs.values_list(
                    "eve_moon__eve_planet__eve_solar_system__eve_constellation__eve_region__name",
                    flat=True,
                )
            elif column == "constellation_name":
                options = qs.values_list(
                    "eve_moon__eve_planet__eve_solar_system__eve_constellation__name",
                    flat=True,
                )
            elif column == "solar_system_name":
                options = qs.values_list(
                    "eve_moon__eve_planet__eve_solar_system__name",
                    flat=True,
                )
            elif column == "rarity_class_str":
                options = qs.values_list("rarity_class_str", flat=True)
            elif column == "label_name":
                options = qs.exclude(label__isnull=True).values_list(
                    "label__name", flat=True
                )
            elif column == "has_refinery_str":
                options = qs.values_list("has_refinery_str", flat=True)
            elif column == "has_extraction_str":
                options = qs.values_list("has_extraction_str", flat=True)
            else:
                options = [f"** ERROR: Invalid column name '{column}' **"]
            result[column] = sorted(list(set(options)), key=str.casefold)
    return JsonResponse(result, safe=False)


@login_required
@permission_required("moonmining.basic_access")
def moon_details(request, moon_pk: int):
    try:
        moon = Moon.objects.selected_related_defaults().get(pk=moon_pk)
    except Moon.DoesNotExist:
        return HttpResponseNotFound()
    if not request.user.has_perm("moonmining.extractions_access"):
        return HttpResponseUnauthorized()
    context = {
        "page_title": moon.name,
        "moon": moon,
        "use_reprocess_pricing": MOONMINING_USE_REPROCESS_PRICING,
        "reprocessing_yield": MOONMINING_REPROCESSING_YIELD * 100,
        "total_volume_per_month": MOONMINING_VOLUME_PER_MONTH / 1000000,
    }
    if request.GET.get("new_page"):
        context["title"] = "Moon"
        context["content_file"] = "moonmining/partials/moon_details.html"
        return render(request, "moonmining/_generic_modal_page.html", context)
    return render(request, "moonmining/modals/moon_details.html", context)


@permission_required(["moonmining.add_refinery_owner", "moonmining.basic_access"])
@token_required(scopes=Owner.esi_scopes())
@login_required
def add_owner(request, token):
    try:
        character_ownership = request.user.character_ownerships.select_related(
            "character"
        ).get(character__character_id=token.character_id)
    except CharacterOwnership.DoesNotExist:
        return HttpResponseNotFound()
    try:
        corporation = EveCorporationInfo.objects.get(
            corporation_id=character_ownership.character.corporation_id
        )
    except EveCorporationInfo.DoesNotExist:
        corporation = EveCorporationInfo.objects.create_corporation(
            corp_id=character_ownership.character.corporation_id
        )
        corporation.save()

    owner, _ = Owner.objects.update_or_create(
        corporation=corporation,
        defaults={"character_ownership": character_ownership},
    )
    tasks.update_owner.delay(owner.pk)
    messages_plus.success(request, f"Update of refineres started for {owner}.")
    if MOONMINING_ADMIN_NOTIFICATIONS_ENABLED:
        notify_admins(
            message=("%(corporation)s was added as new owner by %(user)s.")
            % {"corporation": owner, "user": request.user},
            title=f"{__title__}: Owner added: {owner}",
        )
    return redirect("moonmining:index")


@permission_required(["moonmining.basic_access", "moonmining.upload_moon_scan"])
@login_required()
def upload_survey(request):
    context = {"page_title": "Upload Moon Surveys"}
    if request.method == "POST":
        form = MoonScanForm(request.POST)
        if form.is_valid():
            scans = request.POST["scan"]
            tasks.process_survey_input.delay(scans, request.user.pk)
            messages_plus.success(
                request,
                (
                    "Your scan has been submitted for processing. You will"
                    "receive a notification once processing is complete."
                ),
            )
        else:
            messages_plus.error(
                request,
                (
                    "Oh No! Something went wrong with your moon scan submission. "
                    "Please try again."
                ),
            )
        return redirect("moonmining:moons")
    return render(request, "moonmining/modals/upload_survey.html", context=context)


def previous_month(obj: dt.datetime) -> dt.datetime:
    first = obj.replace(day=1)
    return first - dt.timedelta(days=1)


@login_required()
@permission_required(["moonmining.basic_access", "moonmining.reports_access"])
def reports(request):
    month_minus_1 = previous_month(now())
    month_minus_2 = previous_month(month_minus_1)
    month_minus_3 = previous_month(month_minus_2)
    month_format = "%b '%y"
    if (
        Refinery.objects.filter(
            owner__is_enabled=True, ledger_last_update_at__isnull=False
        )
        .exclude(ledger_last_update_ok=True)
        .exists()
    ):
        ledger_last_updated = None
    else:
        try:
            ledger_last_updated = Refinery.objects.filter(
                owner__is_enabled=True
            ).aggregate(Min("ledger_last_update_at"))["ledger_last_update_at__min"]
        except KeyError:
            ledger_last_updated = None
    context = {
        "page_title": "Reports",
        "use_reprocess_pricing": MOONMINING_USE_REPROCESS_PRICING,
        "reprocessing_yield": MOONMINING_REPROCESSING_YIELD * 100,
        "total_volume_per_month": MOONMINING_VOLUME_PER_MONTH / 1000000,
        "month_minus_3": month_minus_3.strftime(month_format),
        "month_minus_2": month_minus_2.strftime(month_format),
        "month_minus_1": month_minus_1.strftime(month_format),
        "month_current": now().strftime(month_format),
        "ledger_last_updated": ledger_last_updated,
    }
    return render(request, "moonmining/reports.html", context)


@login_required()
@permission_required(["moonmining.basic_access", "moonmining.reports_access"])
def report_owned_value_data(request):
    moon_query = Moon.objects.select_related(
        "eve_moon",
        "eve_moon__eve_planet__eve_solar_system",
        "eve_moon__eve_planet__eve_solar_system__eve_constellation__eve_region",
        "refinery",
        "refinery__owner",
        "refinery__owner__corporation",
        "refinery__owner__corporation__alliance",
    ).filter(refinery__isnull=False)
    corporation_moons = defaultdict(lambda: {"moons": list(), "total": 0})
    for moon in moon_query.order_by("eve_moon__name"):
        corporation_name = moon.refinery.owner.name
        corporation_moons[corporation_name]["moons"].append(moon)
        corporation_moons[corporation_name]["total"] += default_if_none(moon.value, 0)

    moon_ranks = {
        moon_pk: rank
        for rank, moon_pk in enumerate(
            moon_query.filter(value__isnull=False)
            .order_by("-value")
            .values_list("pk", flat=True)
        )
    }
    grand_total = sum(
        [corporation["total"] for corporation in corporation_moons.values()]
    )
    data = list()
    for corporation_name, details in corporation_moons.items():
        corporation = f"{corporation_name} ({len(details['moons'])})"
        counter = 0
        for moon in details["moons"]:
            grand_total_percent = (
                default_if_none(moon.value, 0) / grand_total * 100
                if grand_total > 0
                else None
            )
            rank = moon_ranks[moon.pk] + 1 if moon.pk in moon_ranks else None
            data.append(
                {
                    "corporation": corporation,
                    "moon": {"display": moon_link_html(moon), "sort": counter},
                    "region": moon.region().name,
                    "rarity_class": moon.rarity_tag_html,
                    "value": moon.value,
                    "rank": rank,
                    "total": None,
                    "is_total": False,
                    "grand_total_percent": grand_total_percent,
                }
            )
            counter += 1
        data.append(
            {
                "corporation": corporation,
                "moon": {"display": "TOTAL", "sort": counter},
                "region": None,
                "rarity_class": None,
                "value": None,
                "rank": None,
                "total": details["total"],
                "is_total": True,
                "grand_total_percent": None,
            }
        )
    return JsonResponse(data, safe=False)


@login_required()
@permission_required(["moonmining.basic_access", "moonmining.reports_access"])
def report_user_mining_data(request):
    sum_volume = ExpressionWrapper(
        F("mining_ledger__quantity") * F("mining_ledger__ore_type__volume"),
        output_field=FloatField(),
    )
    sum_price = ExpressionWrapper(
        F("mining_ledger__quantity")
        * Coalesce(F("mining_ledger__ore_type__extras__current_price"), 0),
        output_field=FloatField(),
    )
    today = now()
    months_1 = today.replace(day=1) - dt.timedelta(days=1)
    months_2 = months_1.replace(day=1) - dt.timedelta(days=1)
    months_3 = months_2.replace(day=1) - dt.timedelta(days=1)
    users_mining_totals = (
        User.objects.filter(profile__main_character__isnull=False)
        .select_related("profile__main_character", "profile__state")
        .annotate(
            volume_month_0=Sum(
                sum_volume,
                filter=Q(
                    mining_ledger__day__month=today.month,
                    mining_ledger__day__year=today.year,
                ),
                distinct=True,
            )
        )
        .annotate(
            volume_month_1=Sum(
                sum_volume,
                filter=Q(
                    mining_ledger__day__month=months_1.month,
                    mining_ledger__day__year=months_1.year,
                ),
                distinct=True,
            )
        )
        .annotate(
            volume_month_2=Sum(
                sum_volume,
                filter=Q(
                    mining_ledger__day__month=months_2.month,
                    mining_ledger__day__year=months_2.year,
                ),
                distinct=True,
            )
        )
        .annotate(
            volume_month_3=Sum(
                sum_volume,
                filter=Q(
                    mining_ledger__day__month=months_3.month,
                    mining_ledger__day__year=months_3.year,
                ),
                distinct=True,
            )
        )
        .annotate(
            price_month_0=Sum(
                sum_price,
                filter=Q(
                    mining_ledger__day__month=today.month,
                    mining_ledger__day__year=today.year,
                ),
                distinct=True,
            )
        )
        .annotate(
            price_month_1=Sum(
                sum_price,
                filter=Q(
                    mining_ledger__day__month=months_1.month,
                    mining_ledger__day__year=months_1.year,
                ),
                distinct=True,
            )
        )
        .annotate(
            price_month_2=Sum(
                sum_price,
                filter=Q(
                    mining_ledger__day__month=months_2.month,
                    mining_ledger__day__year=months_2.year,
                ),
                distinct=True,
            )
        )
        .annotate(
            price_month_3=Sum(
                sum_price,
                filter=Q(
                    mining_ledger__day__month=months_3.month,
                    mining_ledger__day__year=months_3.year,
                ),
                distinct=True,
            )
        )
    )
    data = list()
    for user in users_mining_totals:
        corporation_name = user.profile.main_character.corporation_name
        if user.profile.main_character.alliance_ticker:
            corporation_name += f" [{user.profile.main_character.alliance_ticker}]"
        if any(
            [
                user.volume_month_0,
                user.volume_month_1,
                user.volume_month_2,
                user.volume_month_3,
            ]
        ):
            data.append(
                {
                    "id": user.id,
                    "name": str(user.profile.main_character),
                    "corporation": corporation_name,
                    "state": str(user.profile.state),
                    "volume_month_0": default_if_false(user.volume_month_0, 0),
                    "volume_month_1": default_if_false(user.volume_month_1, 0),
                    "volume_month_2": default_if_false(user.volume_month_2, 0),
                    "volume_month_3": default_if_false(user.volume_month_3, 0),
                    "price_month_0": default_if_false(user.price_month_0, 0),
                    "price_month_1": default_if_false(user.price_month_1, 0),
                    "price_month_2": default_if_false(user.price_month_2, 0),
                    "price_month_3": default_if_false(user.price_month_3, 0),
                }
            )
    return JsonResponse(data, safe=False)


@login_required()
@permission_required(["moonmining.basic_access", "moonmining.reports_access"])
def report_user_uploaded_data(request) -> JsonResponse:
    data = list(
        Moon.objects.values(
            name=F("products_updated_by__profile__main_character__character_name"),
            corporation=F(
                "products_updated_by__profile__main_character__corporation_name"
            ),
            state=F("products_updated_by__profile__state__name"),
        ).annotate(num_moons=Count("eve_moon_id"))
    )
    for row in data:
        if row["name"] is None:
            row["name"] = "?"
        if row["corporation"] is None:
            row["corporation"] = "?"
        if row["state"] is None:
            row["state"] = "?"
    return JsonResponse(data, safe=False)


@login_required()
@permission_required(["moonmining.basic_access", "moonmining.reports_access"])
def report_ore_prices_data(request) -> JsonResponse:
    moon_ore_group_ids = [
        EveGroupId.UNCOMMON_MOON_ASTEROIDS,
        EveGroupId.UBIQUITOUS_MOON_ASTEROIDS,
        EveGroupId.EXCEPTIONAL_MOON_ASTEROIDS,
        EveGroupId.COMMON_MOON_ASTEROIDS,
        EveGroupId.RARE_MOON_ASTEROIDS,
    ]
    qs = (
        EveOreType.objects.filter(
            eve_group_id__in=moon_ore_group_ids,
            published=True,
            extras__isnull=False,
            extras__current_price__isnull=False,
        )
        .exclude(name__icontains=" ")
        .select_related("eve_group", "extras")
    )
    data = [
        {
            "id": obj.id,
            "name": obj.name,
            "description": strip_tags(obj.description),
            "price": obj.extras.current_price,
            "group": obj.eve_group.name,
            "rarity_html": {
                "display": obj.rarity_class.bootstrap_tag_html,
                "sort": obj.rarity_class.label,
            },
            "rarity_str": obj.rarity_class.label,
        }
        for obj in qs
    ]
    return JsonResponse(data, safe=False)


@cache_page(3600)
def modal_loader_body(request):
    """Draw the loader body. Useful for showing a spinner while loading a modal."""
    return render(request, "moonmining/modals/loader_body.html")


def tests(request):
    """Render page with JS tests."""
    return render(request, "moonmining/tests.html")
