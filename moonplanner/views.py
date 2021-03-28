import datetime as dt
from collections import defaultdict
from enum import Enum, IntEnum

from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Sum
from django.http import HttpResponseNotFound, JsonResponse
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

from . import __title__, constants, helpers, tasks
from .app_settings import (
    MOONPLANNER_EXTRACTIONS_HOURS_UNTIL_STALE,
    MOONPLANNER_REPROCESSING_YIELD,
    MOONPLANNER_VOLUME_PER_MONTH,
)
from .forms import MoonScanForm
from .helpers import HttpResponseUnauthorized
from .models import Extraction, MiningCorporation, Moon, MoonProduct

# from django.views.decorators.cache import cache_page


logger = LoggerAddTag(get_extension_logger(__name__), __title__)

VALUE_DIVIDER = 1_000_000_000


class IconSize(IntEnum):
    SMALL = 32
    MEDIUM = 64


class ExtractionsCategory(str, helpers.EnumToDict, Enum):
    UPCOMING = "upcoming"
    PAST = "past"


class MoonsCategory(str, helpers.EnumToDict, Enum):
    ALL = "all_moons"
    UPLOADS = "uploads"
    OURS = "our_moons"


def moon_details_button_html(moon: Moon) -> str:
    return fontawesome_link_button_html(
        url=reverse("moonplanner:moon_details", args=[moon.pk]),
        fa_code="fas fa-eye",
        tooltip="Show details in current window",
        button_type="default",
    )


def mining_corporation_html(corporation: MiningCorporation):
    return bootstrap_icon_plus_name_html(
        corporation.eve_corporation.logo_url(size=IconSize.SMALL),
        corporation.name,
        size=IconSize.SMALL,
    )


@login_required
@permission_required("moonplanner.basic_access")
def index(request):
    return redirect("moonplanner:moons")


@login_required
@permission_required(["moonplanner.extractions_access", "moonplanner.basic_access"])
def extractions(request):
    context = {
        "page_title": "Extractions",
        "ExtractionsCategory": ExtractionsCategory.to_dict(),
        "reprocessing_yield": MOONPLANNER_REPROCESSING_YIELD * 100,
        "total_volume_per_month": MOONPLANNER_VOLUME_PER_MONTH / 1000000,
        "stale_hours": MOONPLANNER_EXTRACTIONS_HOURS_UNTIL_STALE,
    }
    return render(request, "moonplanner/extractions.html", context)


@login_required
@permission_required(["moonplanner.extractions_access", "moonplanner.basic_access"])
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
    if category == ExtractionsCategory.PAST:
        extractions = extractions.filter(ready_time__lt=cutover_dt)
    elif category == ExtractionsCategory.UPCOMING:
        extractions = extractions.filter(ready_time__gte=cutover_dt)
    else:
        extractions = Extraction.objects.none()
    for extraction in extractions:
        corporation_html = mining_corporation_html(extraction.refinery.corporation)
        corporation_name = extraction.refinery.corporation.name
        alliance_name = extraction.refinery.corporation.alliance_name
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
                "value": extraction.value / VALUE_DIVIDER if extraction.value else None,
                "details": moon_details_button_html(extraction.refinery.moon),
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
    if not request.user.has_perm(
        "moonplanner.view_all_moons"
    ) and not request.user.has_perm("moonplanner.extractions_access"):
        return HttpResponseUnauthorized()

    product_rows = [
        {
            "ore_type_name": product.ore_type.name,
            "ore_type_url": product.ore_type.profile_url,
            "ore_rarity_tag": product.ore_type.rarity_class.tag_html,
            "image_url": product.ore_type.icon_url(IconSize.MEDIUM),
            "amount": int(round(product.amount * 100)),
            "value": product.calc_value(),
        }
        for product in (
            MoonProduct.objects.select_related("ore_type", "ore_type__eve_group")
            .filter(moon=moon)
            .order_by("-ore_type__eve_group_id")
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
            ).order_by("-ore_type__eve_group_id"):
                value = product.calc_value()
                total_value += value if value else 0
                total_volume += product.volume
                next_pull_product_rows.append(
                    {
                        "ore_type_name": product.ore_type.name,
                        "ore_type_url": product.ore_type.profile_url,
                        "ore_rarity_tag": product.ore_type.rarity_class.tag_html,
                        "image_url": product.ore_type.icon_url(IconSize.SMALL),
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
        "MoonsCategory": MoonsCategory.to_dict(),
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
    if category == MoonsCategory.ALL and request.user.has_perm(
        "moonplanner.view_all_moons"
    ):
        pass
    elif category == MoonsCategory.OURS and request.user.has_perm(
        "moonplanner.extractions_access"
    ):
        moon_query = moon_query.filter(refinery__isnull=False)
    elif category == MoonsCategory.UPLOADS and request.user.has_perm(
        "moonplanner.upload_moon_scan"
    ):
        moon_query = moon_query.filter(products_updated_by=request.user)
    else:
        return JsonResponse([], safe=False)

    for moon in moon_query:
        solar_system_name = moon.eve_moon.eve_planet.eve_solar_system.name
        solar_system_link = link_html(
            dotlan.solar_system_url(solar_system_name), solar_system_name
        )
        has_refinery = hasattr(moon, "refinery")
        if has_refinery:
            corporation_html = mining_corporation_html(moon.refinery.corporation)
            corporation_name = moon.refinery.corporation.name
            alliance_name = moon.refinery.corporation.alliance_name
            has_details_access = request.user.has_perm(
                "moonplanner.extractions_access"
            ) or request.user.has_perm("moonplanner.view_all_moons")
        else:
            corporation_html = corporation_name = alliance_name = ""
            has_details_access = request.user.has_perm("moonplanner.view_all_moons")
        region_name = (
            moon.eve_moon.eve_planet.eve_solar_system.eve_constellation.eve_region.name
        )
        details_html = moon_details_button_html(moon) if has_details_access else ""
        moon_data = {
            "id": moon.pk,
            "moon_name": moon.eve_moon.name,
            "corporation": {"display": corporation_html, "sort": corporation_name},
            "solar_system_link": solar_system_link,
            "region_name": region_name,
            "value": moon.value / VALUE_DIVIDER if moon.value else None,
            "rarity_class": {
                "display": moon.rarity_tag_html,
                "sort": moon.rarity_class,
            },
            "details": details_html,
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


@login_required()
@permission_required(["moonplanner.basic_access", "moonplanner.reports_access"])
def reports(request):
    context = {
        "page_title": "Reports",
        "reprocessing_yield": MOONPLANNER_REPROCESSING_YIELD * 100,
        "total_volume_per_month": MOONPLANNER_VOLUME_PER_MONTH / 1000000,
    }
    return render(request, "moonplanner/reports.html", context)


@login_required()
@permission_required(["moonplanner.basic_access", "moonplanner.reports_access"])
def report_owned_value_data(request):
    moon_query = Moon.objects.select_related(
        "eve_moon",
        "eve_moon__eve_planet__eve_solar_system",
        "eve_moon__eve_planet__eve_solar_system__eve_constellation__eve_region",
        "refinery",
        "refinery__corporation",
        "refinery__corporation__eve_corporation",
        "refinery__corporation__eve_corporation__alliance",
    ).filter(refinery__isnull=False)
    corporation_moons = defaultdict(lambda: {"moons": list(), "total": 0})
    for moon in moon_query.order_by("eve_moon__name"):
        corporation_name = moon.refinery.corporation.name
        moon_value = moon.value / VALUE_DIVIDER if moon.value else 0
        corporation_moons[corporation_name]["moons"].append(
            {
                "pk": moon.pk,
                "name": moon.name,
                "value": moon_value,
                "region": moon.eve_moon.eve_planet.eve_solar_system.eve_constellation.eve_region.name,
            }
        )
        corporation_moons[corporation_name]["total"] += moon_value

    moon_ranks = {
        moon_pk: rank
        for rank, moon_pk in enumerate(
            moon_query.order_by("-value").values_list("pk", flat=True)
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
            data.append(
                {
                    "corporation": corporation,
                    "moon": {"display": moon["name"], "sort": counter},
                    "region": moon["region"],
                    "value": moon["value"],
                    "rank": moon_ranks[moon["pk"]] + 1,
                    "total": None,
                    "is_total": False,
                    "grand_total_percent": moon["value"] / grand_total * 100,
                }
            )
            counter += 1
        data.append(
            {
                "corporation": corporation,
                "moon": {"display": "TOTAL", "sort": counter},
                "region": None,
                "value": None,
                "rank": None,
                "total": details["total"],
                "is_total": True,
                "grand_total_percent": None,
            }
        )
    return JsonResponse(data, safe=False)
