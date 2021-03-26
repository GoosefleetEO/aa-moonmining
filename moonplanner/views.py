import datetime as dt

from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Sum
from django.http import HttpResponse, HttpResponseNotFound, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.timezone import now
from esi.decorators import token_required

from allianceauth.authentication.models import CharacterOwnership
from allianceauth.eveonline.evelinks import dotlan
from allianceauth.eveonline.models import EveCorporationInfo
from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag
from app_utils.messages import messages_plus
from app_utils.views import (
    bootstrap_icon_plus_name_html,
    fontawesome_link_button_html,
    link_html,
)

from . import __title__, constants, tasks
from .app_settings import (
    MOONPLANNER_EXTRACTIONS_HOURS_UNTIL_STALE,
    MOONPLANNER_REPROCESSING_YIELD,
    MOONPLANNER_VOLUME_PER_MONTH,
)
from .forms import MoonScanForm
from .models import Extraction, MiningCorporation, Moon, MoonProduct

# from django.views.decorators.cache import cache_page


logger = LoggerAddTag(get_extension_logger(__name__), __title__)

MOONS_CATEGORY_ALL = "all_moons"
MOONS_CATEGORY_OURS = "our_moons"
EXTRACTIONS_CATEGORY_UPCOMING = "upcoming"
EXTRACTIONS_CATEGORY_PAST = "past"
ICON_SIZE_SMALL = 32
ICON_SIZE_MEDIUM = 64


class HttpResponseUnauthorized(HttpResponse):
    status_code = 401


def moon_details_button(moon: Moon) -> str:
    return fontawesome_link_button_html(
        url=reverse("moonplanner:moon_details", args=[moon.pk]),
        fa_code="fas fa-eye",
        tooltip="Show details in current window",
        button_type="default",
    )


def corporation_names(corporation: MiningCorporation):
    if corporation:
        corporation_name = str(corporation)
        corporation_html = bootstrap_icon_plus_name_html(
            corporation.eve_corporation.logo_url(size=ICON_SIZE_MEDIUM),
            corporation_name,
            size=40,
        )
        alliance_name = (
            corporation.eve_corporation.alliance.alliance_name
            if corporation.eve_corporation.alliance
            else ""
        )
    else:
        alliance_name = corporation_name = corporation_html = ""
    return corporation_html, corporation_name, alliance_name


@login_required
@permission_required("moonplanner.basic_access")
def index(request):
    return redirect("moonplanner:moons")


@login_required
@permission_required(["moonplanner.access_our_moons", "moonplanner.basic_access"])
def extractions(request):
    context = {
        "page_title": "Extractions",
        "reprocessing_yield": MOONPLANNER_REPROCESSING_YIELD * 100,
        "total_volume_per_month": MOONPLANNER_VOLUME_PER_MONTH / 1000000,
        "stale_hours": MOONPLANNER_EXTRACTIONS_HOURS_UNTIL_STALE,
    }
    return render(request, "moonplanner/extractions.html", context)


@login_required
@permission_required(["moonplanner.access_our_moons", "moonplanner.basic_access"])
def extractions_data(request, category):
    data = list()
    cutover_dt = now() - dt.timedelta(hours=MOONPLANNER_EXTRACTIONS_HOURS_UNTIL_STALE)
    extractions = Extraction.objects.select_related(
        "refinery",
        "refinery__moon",
        "refinery__corporation",
        "refinery__corporation__eve_corporation",
        "refinery__corporation__eve_corporation__alliance",
    ).annotate(volume=Sum("products__volume"))
    if category == EXTRACTIONS_CATEGORY_PAST:
        extractions = extractions.filter(ready_time__lt=cutover_dt)
    elif category == EXTRACTIONS_CATEGORY_UPCOMING:
        extractions = extractions.filter(ready_time__gte=cutover_dt)
    else:
        extractions = Extraction.objects.none()
    for extraction in extractions:
        (
            corporation_html,
            corporation_name,
            alliance_name,
        ) = corporation_names(extraction.refinery.corporation)
        data.append(
            {
                "id": extraction.pk,
                "ready_time": {
                    "display": extraction.ready_time.strftime(
                        constants.DATETIME_FORMAT
                    ),
                    "sort": extraction.ready_time,
                },
                "moon": str(extraction.refinery.moon),
                "corporation": {"display": corporation_html, "sort": corporation_name},
                "volume": extraction.volume,
                "value": extraction.value / 1000000000 if extraction.value else None,
                "details": moon_details_button(extraction.refinery.moon),
                "corporation_name": corporation_name,
                "alliance_name": alliance_name,
                "is_ready": extraction.ready_time <= now(),
            }
        )
    return JsonResponse(data, safe=False)


@login_required
@permission_required("moonplanner.basic_access")
def moon_details(request, moon_pk: int):
    try:
        moon = Moon.objects.select_related("eve_moon").get(pk=moon_pk)
    except Moon.DoesNotExist:
        return HttpResponseNotFound()
    if not request.user.has_perm("moonplanner.access_all_moons") or (
        moon.is_owned and not request.user.has_perm("moonplanner.access_our_moons")
    ):
        return HttpResponseUnauthorized()

    product_rows = [
        {
            "ore_type_name": product.ore_type.name,
            "ore_type_url": product.ore_type.profile_url,
            "ore_group_name": product.ore_type.eve_group.name,
            "image_url": product.ore_type.icon_url(ICON_SIZE_MEDIUM),
            "amount": int(round(product.amount * 100)),
            "value": product.calc_value(),
        }
        for product in (
            MoonProduct.objects.select_related("ore_type", "ore_type__eve_group")
            .filter(moon=moon)
            .order_by("ore_type__name")
        )
    ]
    next_pull_data = None
    ppulls_data = None
    if hasattr(moon, "refinery"):
        next_pull = Extraction.objects.filter(
            refinery=moon.refinery, ready_time__gte=now()
        ).first()
        if next_pull:
            next_pull_product_rows = list()
            total_value = 0
            total_volume = 0
            for product in next_pull.products.select_related(
                "ore_type", "ore_type__eve_group"
            ).order_by("ore_type__name"):
                value = product.calc_value()
                total_value += value if value else 0
                total_volume += product.volume
                next_pull_product_rows.append(
                    {
                        "ore_type_name": product.ore_type.name,
                        "ore_type_url": product.ore_type.profile_url,
                        "ore_group_name": product.ore_type.eve_group.name,
                        "image_url": product.ore_type.icon_url(ICON_SIZE_SMALL),
                        "volume": product.volume,
                        "value": value,
                    }
                )
            next_pull_data = {
                "ready_time": next_pull.ready_time,
                "auto_time": next_pull.auto_time,
                "started_by": next_pull.started_by,
                "total_value": total_value,
                "total_volume": total_volume,
                "products": next_pull_product_rows,
            }
            ppulls_data = Extraction.objects.filter(
                refinery=moon.refinery, ready_time__lt=now()
            )

    context = {
        "page_title": "Moon Detail",
        "moon": moon,
        "product_rows": product_rows,
        "next_pull": next_pull_data,
        "ppulls": ppulls_data,
        "reprocessing_yield": MOONPLANNER_REPROCESSING_YIELD * 100,
        "total_volume_per_month": MOONPLANNER_VOLUME_PER_MONTH / 1000000,
    }
    return render(request, "moonplanner/moon_details.html", context)


@permission_required(["moonplanner.basic_access", "moonplanner.upload_moon_scan"])
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
            return render(request, "moonplanner/add_scan.html", context=context)
        else:
            messages_plus.error(
                request, "Oh No! Something went wrong with your moon scan submission."
            )
            return redirect("moonplanner:moon_details")
    else:
        return render(request, "moonplanner/add_scan.html", context=context)


@login_required()
@permission_required("moonplanner.basic_access")
def moons(request):
    context = {
        "page_title": "Moons",
        "reprocessing_yield": MOONPLANNER_REPROCESSING_YIELD * 100,
        "total_volume_per_month": MOONPLANNER_VOLUME_PER_MONTH / 1000000,
    }
    return render(request, "moonplanner/moons.html", context)


# @cache_page(60 * 5) TODO: Remove for release
@login_required()
@permission_required("moonplanner.basic_access")
def moons_data(request, category):
    """returns moon list in JSON for DataTables AJAX"""
    data = list()
    moon_query = Moon.objects.select_related(
        "eve_moon",
        "eve_moon__eve_planet__eve_solar_system",
        "eve_moon__eve_planet__eve_solar_system__eve_constellation__eve_region",
        "refinery",
        "refinery__corporation",
        "refinery__corporation__eve_corporation",
        "refinery__corporation__eve_corporation__alliance",
    )
    if category == MOONS_CATEGORY_ALL:
        if not request.user.has_perm("moonplanner.access_all_moons"):
            return JsonResponse([], safe=False)
    else:
        moon_query = moon_query.filter(refinery__isnull=False)
        if not request.user.has_perm("moonplanner.access_our_moons"):
            return JsonResponse([], safe=False)

    for moon in moon_query:
        solar_system_name = moon.eve_moon.eve_planet.eve_solar_system.name
        solar_system_link = link_html(
            dotlan.solar_system_url(solar_system_name), solar_system_name
        )
        has_refinery = hasattr(moon, "refinery")
        (
            corporation_html,
            corporation_name,
            alliance_name,
        ) = corporation_names(moon.refinery.corporation if has_refinery else None)
        region_name = (
            moon.eve_moon.eve_planet.eve_solar_system.eve_constellation.eve_region.name
        )
        moon_data = {
            "id": moon.pk,
            "moon_name": moon.eve_moon.name,
            "corporation": {"display": corporation_html, "sort": corporation_name},
            "solar_system_link": solar_system_link,
            "region_name": region_name,
            "value": moon.value / 1000000000 if moon.value else None,
            "details": moon_details_button(moon),
            "has_refinery_str": "yes" if has_refinery else "no",
            "solar_system_name": solar_system_name,
            "corporation_name": corporation_name,
            "alliance_name": alliance_name,
            "has_refinery": has_refinery,
        }
        data.append(moon_data)
    return JsonResponse(data, safe=False)


@permission_required(["moonplanner.add_corporation", "moonplanner.basic_access"])
@token_required(scopes=MiningCorporation.esi_scopes())
@login_required
def add_corporation(request, token):
    try:
        character_ownership = request.user.character_ownerships.select_related(
            "character"
        ).get(character__character_id=token.character_id)
    except CharacterOwnership.DoesNotExist:
        return HttpResponseNotFound()
    try:
        eve_corporation = EveCorporationInfo.objects.get(
            corporation_id=character_ownership.character.corporation_id
        )
    except EveCorporationInfo.DoesNotExist:
        eve_corporation = EveCorporationInfo.objects.create_corporation(
            corp_id=character_ownership.character.corporation_id
        )
        eve_corporation.save()

    corporation, _ = MiningCorporation.objects.update_or_create(
        eve_corporation=eve_corporation,
        defaults={"character_ownership": character_ownership},
    )
    tasks.update_mining_corporation.delay(corporation.pk)
    messages_plus.success(
        request, f"Update of refineres started for {eve_corporation}."
    )
    return redirect("moonplanner:extractions")
