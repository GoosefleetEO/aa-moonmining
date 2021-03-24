from datetime import datetime, timezone

from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Sum
from django.http import HttpResponse, HttpResponseNotFound, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
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

from . import __title__
from .app_settings import MOONPLANNER_REPROCESSING_YIELD, MOONPLANNER_VOLUME_PER_MONTH
from .forms import MoonScanForm
from .models import Extraction, MiningCorporation, Moon, MoonProduct
from .tasks import process_survey_input, update_mining_corporation

# from django.views.decorators.cache import cache_page


logger = LoggerAddTag(get_extension_logger(__name__), __title__)


URL_PROFILE_TYPE = "https://www.kalkoken.org/apps/eveitems/?typeId="

MOONS_LIST_ALL = "all_moons"
MOONS_LIST_OUR = "our_moons"


class HttpResponseUnauthorized(HttpResponse):
    status_code = 401


@login_required
@permission_required("moonplanner.access_moonplanner")
def index(request):
    return redirect("moonplanner:extractions")

    # TODO
    # if request.user.has_perm("moonplanner.access_all_moons"):
    #     return redirect("moonplanner:moon_list_all")

    # elif request.user.has_perm("moonplanner.access_our_moons"):
    #     return redirect("moonplanner:extractions")

    # elif request.user.has_perm("moonplanner.upload_moon_scan"):
    #     return redirect("moonplanner:add_moon_scan")

    # else:
    #     return HttpResponse("Insufficient permissions to use this app")


@login_required
@permission_required(("moonplanner.access_our_moons", "moonplanner.access_moonplanner"))
def extractions(request):
    # Upcoming Extractions
    today = datetime.today().replace(tzinfo=timezone.utc)
    context = {
        "exts": Extraction.objects.annotate(volume=Sum("products__volume")).filter(
            ready_time__gte=today
        ),
        "r_exts": Extraction.objects.filter(ready_time__lt=today)[:20],
    }
    return render(request, "moonplanner/extractions.html", context)


@login_required
@permission_required("moonplanner.access_moonplanner")
def moon_info(request, moon_pk: int):
    try:
        moon = Moon.objects.select_related("eve_moon").get(pk=moon_pk)
    except Moon.DoesNotExist:
        return HttpResponseNotFound()
    if not request.user.has_perm("moonplanner.access_all_moons") or (
        moon.is_owned and not request.user.has_perm("moonplanner.access_our_moons")
    ):
        return HttpResponseUnauthorized()

    product_rows = []
    for product in (
        MoonProduct.objects.select_related("eve_type", "eve_type__eve_group")
        .filter(moon=moon)
        .order_by("eve_type__name")
    ):
        image_url = product.eve_type.icon_url(64)
        amount = int(round(product.amount * 100))
        ore_type_url = "{}{}".format(URL_PROFILE_TYPE, product.eve_type_id)
        product_rows.append(
            {
                "ore_type_name": product.eve_type.name,
                "ore_type_url": ore_type_url,
                "ore_group_name": product.eve_type.eve_group.name,
                "image_url": image_url,
                "amount": amount,
                "value": product.calc_value(),
            }
        )

    today = datetime.today().replace(tzinfo=timezone.utc)
    next_pull_data = None
    ppulls_data = None
    if hasattr(moon, "refinery"):
        next_pull = Extraction.objects.filter(
            refinery=moon.refinery, ready_time__gte=today
        ).first()
        if next_pull:
            next_pull_product_rows = list()
            total_value = 0
            total_volume = 0
            for product in next_pull.products.select_related(
                "eve_type", "eve_type__eve_group"
            ).order_by("eve_type__name"):
                image_url = product.eve_type.icon_url(32)
                value = product.calc_value_estimate()
                total_value += value if value else 0
                total_volume += product.volume
                ore_type_url = "{}{}".format(URL_PROFILE_TYPE, product.eve_type_id)
                next_pull_product_rows.append(
                    {
                        "ore_type_name": product.eve_type.name,
                        "ore_type_url": ore_type_url,
                        "ore_group_name": product.eve_type.eve_group.name,
                        "image_url": image_url,
                        "volume": product.volume,
                        "value": value,
                    }
                )
            next_pull_data = {
                "ready_time": next_pull.ready_time,
                "auto_time": next_pull.auto_time,
                "total_value": total_value,
                "total_volume": total_volume,
                "products": next_pull_product_rows,
            }
            ppulls_data = Extraction.objects.filter(
                refinery=moon.refinery, ready_time__lt=today
            )

    context = {
        "page_title": moon.eve_moon.name,
        "moon": moon,
        "solar_system": moon.eve_moon.eve_planet.eve_solar_system,
        "moon_name": moon.eve_moon.name,
        "product_rows": product_rows,
        "next_pull": next_pull_data,
        "ppulls": ppulls_data,
        "reprocessing_yield": MOONPLANNER_REPROCESSING_YIELD * 100,
        "total_volume_per_month": MOONPLANNER_VOLUME_PER_MONTH / 1000000,
    }
    return render(request, "moonplanner/moon_info.html", context)


@permission_required(("moonplanner.access_moonplanner", "moonplanner.upload_moon_scan"))
@login_required()
def add_moon_scan(request):
    context = {
        "page_title": "Moon Scan Input",
    }
    if request.method == "POST":
        form = MoonScanForm(request.POST)
        if form.is_valid():
            scans = request.POST["scan"]
            process_survey_input.delay(scans, request.user.pk)
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
            return redirect("moonplanner:moon_info")
    else:
        return render(request, "moonplanner/add_scan.html", context=context)


@login_required()
@permission_required("moonplanner.access_moonplanner")
def moon_list(request):
    context = {
        "page_title": "Moons",
        "reprocessing_yield": MOONPLANNER_REPROCESSING_YIELD * 100,
        "total_volume_per_month": MOONPLANNER_VOLUME_PER_MONTH / 1000000,
    }
    return render(request, "moonplanner/moon_list.html", context)


@login_required()
@permission_required(("moonplanner.access_moonplanner", "moonplanner.access_our_moons"))
def moon_list_ours(request):
    return _moon_list_generic(request, MOONS_LIST_OUR)


@login_required()
@permission_required(("moonplanner.access_moonplanner", "moonplanner.access_all_moons"))
def moon_list_all(request):
    return _moon_list_generic(request, MOONS_LIST_ALL)


def _moon_list_generic(request, category):
    context = {
        "title": "All Moons" if category == MOONS_LIST_ALL else "Our Moons",
        "ajax_url": reverse("moonplanner:moon_list_data", args=[category]),
        "reprocessing_yield": MOONPLANNER_REPROCESSING_YIELD * 100,
        "total_volume_per_month": MOONPLANNER_VOLUME_PER_MONTH / 1000000,
    }
    return render(request, "moonplanner/moon_list.html", context)


# @cache_page(60 * 5) TODO: Remove for release
@login_required()
@permission_required("moonplanner.access_moonplanner")
def moon_list_data(request, category):
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
    if category == MOONS_LIST_OUR:
        moon_query = moon_query.filter(refinery__isnull=False)
        if not request.user.has_perm("moonplanner.access_our_moons"):
            return HttpResponseUnauthorized()
    else:
        if not request.user.has_perm("moonplanner.access_all_moons"):
            return HttpResponseUnauthorized()

    for moon in moon_query:
        moon_details_url = reverse("moonplanner:moon_info", args=[moon.pk])
        solar_system_name = moon.eve_moon.eve_planet.eve_solar_system.name
        solar_system_link = link_html(
            dotlan.solar_system_url(solar_system_name), solar_system_name
        )
        if moon.value is not None:
            value = "{:.1f}".format(moon.value / 1000000000)
        else:
            value = "(no data)"

        has_refinery = hasattr(moon, "refinery")
        if has_refinery:
            eve_corporation = moon.refinery.corporation.eve_corporation
            corporation_name = str(moon.refinery.corporation)
            corporation_html = bootstrap_icon_plus_name_html(
                eve_corporation.logo_url(size=64),
                corporation_name,
                size=40,
            )
            alliance_name = (
                eve_corporation.alliance.alliance_name
                if eve_corporation.alliance
                else ""
            )
        else:
            alliance_name = corporation_name = corporation_html = ""
        region_name = (
            moon.eve_moon.eve_planet.eve_solar_system.eve_constellation.eve_region.name
        )
        details_button = fontawesome_link_button_html(
            url=moon_details_url,
            fa_code="fas fa-eye",
            tooltip="Show details in current window",
            button_type="default",
        )
        moon_data = {
            "id": moon.pk,
            "moon_name": moon.eve_moon.name,
            "corporation": {"display": corporation_html, "sort": corporation_name},
            "solar_system_link": solar_system_link,
            "region_name": region_name,
            "value": value,
            "details": details_button,
            "has_refinery_str": "yes" if has_refinery else "no",
            "solar_system_name": solar_system_name,
            "corporation_name": corporation_name,
            "alliance_name": alliance_name,
            "has_refinery": has_refinery,
        }
        data.append(moon_data)
    return JsonResponse(data, safe=False)


@permission_required(
    ("moonplanner.add_mining_corporation", "moonplanner.access_moonplanner")
)
@token_required(scopes=MiningCorporation.esi_scopes())
@login_required
def add_mining_corporation(request, token):
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
    update_mining_corporation.delay(corporation.pk)
    messages_plus.success(
        request, f"Update of refineres started for {eve_corporation}."
    )
    return redirect("moonplanner:extractions")
