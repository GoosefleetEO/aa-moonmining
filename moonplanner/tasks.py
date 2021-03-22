from app_utils.logging import LoggerAddTag
from celery import shared_task

from django.contrib.auth.models import User
from django.db import transaction
from django.utils.timezone import now

from allianceauth.notifications import notify
from allianceauth.services.hooks import get_extension_logger
from eveuniverse.models import EveMarketPrice, EveMoon, EveType

from . import __title__
from .models import MiningCorporation, Moon, MoonProduct

logger = LoggerAddTag(get_extension_logger(__name__), __title__)


@shared_task
def process_survey_input(scans, user_pk=None):
    """process raw moon survey input from user

    Args:
        scans: raw text input from user containing moon survey data
        user_pk: (optional) id of user who submitted the data
    """
    user = User.objects.get(pk=user_pk) if user_pk else None
    process_results = list()
    try:
        lines = scans.split("\n")
        lines_ = []
        for line in lines:
            line = line.strip("\r").split("\t")
            lines_.append(line)
        lines = lines_

        # Find all groups of scans.
        if len(lines[0]) == 0 or lines[0][0] == "Moon":
            lines = lines[1:]
        sublists = []
        for line in lines:
            # Find the lines that start a scan
            if line[0] == "":
                pass
            else:
                sublists.append(lines.index(line))

        # Separate out individual surveys
        surveys = []
        for i in range(len(sublists)):
            # The First List
            if i == 0:
                if i + 2 > len(sublists):
                    surveys.append(lines[sublists[i] :])
                else:
                    surveys.append(lines[sublists[i] : sublists[i + 1]])
            else:
                if i + 2 > len(sublists):
                    surveys.append(lines[sublists[i] :])
                else:
                    surveys.append(lines[sublists[i] : sublists[i + 1]])

    except Exception as ex:
        logger.warning(
            "An issue occurred while trying to parse the surveys", exc_info=True
        )
        error_name = type(ex).__name__
        success = False

    else:
        success = True
        error_name = None
        moon_name = None
        for survey in surveys:
            try:
                moon_name = survey[0][0]
                moon_id = survey[1][6]
                eve_moon, _ = EveMoon.objects.get_or_create_esi(id=moon_id)
                with transaction.atomic():  # TODO: remove transaction
                    moon, _ = Moon.objects.get_or_create(eve_moon=eve_moon)
                    moon.products_updated_by = user
                    moon.products_updated_at = now()
                    moon.products.all().delete()
                    survey = survey[1:]
                    for product_data in survey:
                        # Trim off the empty index at the front
                        product_data = product_data[1:]
                        eve_type, _ = EveType.objects.get_or_create_esi(
                            id=product_data[2],
                            enabled_sections=[EveType.Section.TYPE_MATERIALS],
                        )
                        MoonProduct.objects.create(
                            moon=moon, amount=product_data[1], eve_type=eve_type
                        )
                moon.update_income_estimate()
                logger.info("Added moon survey for %s", moon.eve_moon.name)

            except Exception as ex:
                logger.warning(
                    "An issue occurred while processing the following moon survey: %s",
                    survey,
                    exc_info=True,
                )
                error_name = type(ex).__name__
                success = False
            else:
                success = True
                error_name = None

            process_results.append(
                {"moon_name": moon_name, "success": success, "error_name": error_name}
            )

    # send result notification to user
    if user:
        message = "We have completed processing your moon survey input:\n\n"
        if process_results:
            n = 0
            for result in process_results:
                n = n + 1
                name = result["moon_name"]
                if result["success"]:
                    status = "OK"
                    error_name = ""
                else:
                    status = "FAILED"
                    success = False
                    error_name = "- {}".format(result["error_name"])
                message += "#{}: {}: {} {}\n".format(n, name, status, error_name)
        else:
            message += f"\nProcessing failed: {error_name}"

        notify(
            user=user,
            title="Moon survey input processing results: {}".format(
                "OK" if success else "FAILED"
            ),
            message=message,
            level="success" if success else "danger",
        )

    return success


@shared_task
def run_refineries_update(mining_corp_pk):
    """update list of refineries with extractions for a mining corporation"""
    mining_corp = MiningCorporation.objects.get(pk=mining_corp_pk)
    mining_corp.update_refineries_from_esi()
    mining_corp.update_extractions_from_esi()


@shared_task
def update_all_moon_income():
    """update the income for all moons"""
    EveMarketPrice.objects.update_from_esi()
    logger.info("Re-calculating moon income for %d moons...", Moon.objects.count())
    for moon in Moon.objects.all():
        update_moon_income.delay(moon.pk)


@shared_task
def update_moon_income(moon_pk):
    moon = Moon.objects.get(pk=moon_pk)
    moon.update_income_estimate()
