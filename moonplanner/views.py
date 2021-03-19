import logging
import urllib
from datetime import datetime, timezone

from app_utils.messages import messages_plus

from django.contrib.auth.decorators import login_required, permission_required
from django.http import HttpResponseForbidden, HttpResponseNotFound, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from allianceauth.eveonline.models import EveCharacter, EveCorporationInfo
from esi.decorators import token_required

from .app_settings import MOONPLANNER_REPROCESSING_YIELD, MOONPLANNER_VOLUME_PER_MONTH
from .forms import MoonScanForm
from .models import Extraction, MiningCorporation, Moon, MoonProduct, Refinery
from .tasks import process_survey_input, run_refineries_update

# from django.views.decorators.cache import cache_page


logger = logging.getLogger(__name__)


URL_PROFILE_SOLAR_SYSTEM = "https://evemaps.dotlan.net/system"
URL_PROFILE_TYPE = "https://www.kalkoken.org/apps/eveitems/?typeId="


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
    ctx = {}
    # Upcoming Extractions
    today = datetime.today().replace(tzinfo=timezone.utc)
    ctx["exts"] = Extraction.objects.filter(ready_time__gte=today)
    ctx["r_exts"] = Extraction.objects.filter(ready_time__lt=today)[:20]
    return render(request, "moonplanner/extractions.html", ctx)


@login_required
@permission_required("moonplanner.access_moonplanner")
def moon_info(request, moonid):
    try:
        moon = Moon.objects.select_related("eve_moon").get(pk=moonid)
    except Moon.DoesNotExist:
        return HttpResponseNotFound()
    if not request.user.has_perm("moonplanner.access_all_moons") or (
        moon.is_owned and not request.user.has_perm("moonplanner.access_our_moons")
    ):
        return HttpResponseForbidden()

    income = moon.calc_income_estimate(
        MOONPLANNER_VOLUME_PER_MONTH, MOONPLANNER_REPROCESSING_YIELD
    )
    product_rows = []
    for product in MoonProduct.objects.select_related(
        "eve_type", "eve_type__eve_group"
    ).filter(moon=moon):
        image_url = product.eve_type.icon_url(64)
        amount = int(round(product.amount * 100))
        income = moon.calc_income_estimate(
            MOONPLANNER_VOLUME_PER_MONTH,
            MOONPLANNER_REPROCESSING_YIELD,
            product,
        )
        ore_type_url = "{}{}".format(URL_PROFILE_TYPE, product.eve_type_id)
        product_rows.append(
            {
                "ore_type_name": product.eve_type.name,
                "ore_type_url": ore_type_url,
                "ore_group_name": product.eve_type.eve_group.name,
                "image_url": image_url,
                "amount": amount,
                "income": None if income is None else income / 1000000000,
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
            ):
                image_url = product.eve_type.icon_url(32)
                value = product.calc_value_estimate(MOONPLANNER_REPROCESSING_YIELD)
                total_value += value
                total_volume += product.volume
                ore_type_url = "{}{}".format(URL_PROFILE_TYPE, product.eve_type_id)

                next_pull_product_rows.append(
                    {
                        "ore_type_name": product.eve_type.name,
                        "ore_type_url": ore_type_url,
                        "ore_group_name": product.eve_type.eve_group.name,
                        "image_url": image_url,
                        "volume": "{:,.0f}".format(product.volume),
                        "value": None if value is None else value / 1000000000,
                    }
                )

            total_value = None if total_value is None else total_value / 1000000000
            next_pull_data = {
                "ready_time": next_pull.ready_time,
                "auto_time": next_pull.auto_time,
                "total_value": total_value,
                "total_volume": "{:,.0f}".format(total_volume),
                "products": next_pull_product_rows,
            }
            ppulls_data = Extraction.objects.filter(
                refinery=moon.refinery, ready_time__lt=today
            )

    context = {
        "moon": moon,
        "solar_system": moon.eve_moon.eve_planet.eve_solar_system,
        "moon_name": moon.eve_moon.name,
        "moon_income": None if income is None else income / 1000000000,
        "product_rows": product_rows,
        "next_pull": next_pull_data,
        "ppulls": ppulls_data,
    }
    return render(request, "moonplanner/moon_info.html", context)


@permission_required(("moonplanner.access_moonplanner", "moonplanner.upload_moon_scan"))
@login_required()
def add_moon_scan(request):
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
            return render(request, "moonplanner/add_scan.html")
        else:
            messages_plus.error(
                request, "Oh No! Something went wrong with your moon scan submission."
            )
            return redirect("moonplanner:moon_info")
    else:
        return render(request, "moonplanner/add_scan.html")


@login_required()
@permission_required(("moonplanner.access_moonplanner", "moonplanner.access_our_moons"))
def moon_list_ours(request):
    # render the page only, data is retrieved through ajax from moon_list_data
    context = {
        "title": "Our Moons",
        "ajax_url": reverse("moonplanner:moon_list_data", args=["our_moons"]),
        "reprocessing_yield": MOONPLANNER_REPROCESSING_YIELD * 100,
        "total_volume_per_month": "{:,.1f}".format(
            MOONPLANNER_VOLUME_PER_MONTH / 1000000
        ),
    }
    return render(request, "moonplanner/moon_list.html", context)


@login_required()
@permission_required(("moonplanner.access_moonplanner", "moonplanner.access_all_moons"))
def moon_list_all(request):
    # render the page only, data is retrieved through ajax from moon_list_data
    context = {
        "title": "All Moons",
        "ajax_url": reverse("moonplanner:moon_list_data", args=["all_moons"]),
        "reprocessing_yield": MOONPLANNER_REPROCESSING_YIELD * 100,
        "total_volume_per_month": "{:,.1f}".format(
            MOONPLANNER_VOLUME_PER_MONTH / 1000000
        ),
    }
    return render(request, "moonplanner/moon_list.html", context)


# @cache_page(60 * 5) TODO: Remove for release
@login_required()
@permission_required("moonplanner.access_moonplanner")
def moon_list_data(request, category):
    """returns moon list in JSON for DataTables AJAX"""
    data = list()
    if category == "our_moons":
        moon_query = [r.moon for r in Refinery.objects.select_related("moon")]
    else:
        moon_query = Moon.objects.select_related(
            "eve_moon",
            "eve_moon__eve_planet__eve_solar_system__eve_constellation__eve_region",
            "refinery",
        )
    for moon in moon_query:
        moon_details_url = reverse("moonplanner:moon_info", args=[moon.pk])
        solar_system_name = moon.eve_moon.eve_planet.eve_solar_system.name
        solar_system_link = '<a href="{}/{}" target="_blank">{}</a>'.format(
            URL_PROFILE_SOLAR_SYSTEM,
            urllib.parse.quote_plus(solar_system_name),
            solar_system_name,
        )

        if moon.income is not None:
            income = "{:.1f}".format(moon.income / 1000000000)
        else:
            income = "(no data)"

        has_refinery = hasattr(moon, "refinery")
        corporation = str(moon.refinery.corporation) if has_refinery else ""

        moon_data = {
            "id": moon.pk,
            "moon_name": moon.eve_moon.name,
            "corporation": corporation,
            "solar_system_name": solar_system_name,
            "solar_system_link": solar_system_link,
            "region_name": moon.eve_moon.eve_planet.eve_solar_system.eve_constellation.eve_region.name,
            "income": income,
            "has_refinery": has_refinery,
            "has_refinery_str": "yes" if has_refinery else "no",
            "details": (
                f'<a class="btn btn-primary btn-sm" href="{moon_details_url}" '
                'data-toggle="tooltip" data-placement="top" '
                'title="Show details in current window">'
                '<i class="fas fa-eye"></i></a>&nbsp;&nbsp;'
                f'<a class="btn btn-default btn-sm" href="{moon_details_url}" '
                'target="_blank" data-toggle="tooltip" data-placement="top" '
                'title="Open details in new window">'
                '<i class="fas fa-window-restore"></i></a>'
            ),
        }
        data.append(moon_data)
    return JsonResponse(data, safe=False)


@permission_required(
    ("moonplanner.add_mining_corporation", "moonplanner.access_moonplanner")
)
@token_required(scopes=MiningCorporation.get_esi_scopes())
@login_required
def add_mining_corporation(request, token):
    character = EveCharacter.objects.get(character_id=token.character_id)
    try:
        corporation = EveCorporationInfo.objects.get(
            corporation_id=character.corporation_id
        )
    except EveCorporationInfo.DoesNotExist:
        corporation = EveCorporationInfo.objects.create_corporation(
            corp_id=character.corporation_id
        )
        corporation.save()

    mining_corporation, _ = MiningCorporation.objects.get_or_create(
        corporation=corporation, defaults={"character": character}
    )
    run_refineries_update.delay(mining_corporation.pk, request.user.pk)
    messages_plus.success(
        request,
        "Update of refineres started for {}. ".format(corporation)
        + "You will receive a notifications with results shortly.",
    )
    return redirect("moonplanner:extractions")
