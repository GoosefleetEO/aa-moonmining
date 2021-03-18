import logging

import yaml
from app_utils.datetime import ldap_time_2_datetime
from app_utils.logging import LoggerAddTag, make_logger_prefix
from celery import shared_task

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction

from allianceauth.eveonline.models import EveCharacter
from allianceauth.notifications import notify
from eveuniverse.models import EveMarketPrice, EveSolarSystem, EveType

from . import __title__
from .app_settings import MOONPLANNER_REPROCESSING_YIELD, MOONPLANNER_VOLUME_PER_MONTH
from .models import (  # MarketPrice,; Moon,
    Extraction,
    ExtractionProduct,
    MiningCorporation,
    MoonIncome,
    MoonProduct,
    Refinery,
)
from .providers import esi

# from evesde.models import EveSolarSystem, EveType


# add custom tag to logger with name of this app
logger = LoggerAddTag(logging.getLogger(__name__), __title__)

REFINERY_GROUP_ID = 1406
MOON_GROUP_ID = 8
MAX_DISTANCE_TO_MOON_METERS = 3000000


"""
def _get_tokens(scopes):
    try:
        tokens = []
        characters = MoonDataCharacter.objects.all()
        for character in characters:
            tokens.append(Token.objects.filter(character_id=character.character.character_id).require_scopes(scopes)[0])
        return tokens
    except Exception as e:
        print(e)
        return False
"""


@shared_task
def process_survey_input(scans, user_pk=None):
    """process raw moon survey input from user

    Args:
        scans: raw text input from user containing moon survey data
        user_pk: (optional) id of user who submitted the data
    """
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
                with transaction.atomic():
                    moon_name = survey[0][0]
                    solar_system_id = survey[1][4]
                    moon_id = survey[1][6]
                    moon, _ = MoonIncome.objects.get_or_create(
                        moon_id=moon_id,
                        defaults={"solar_system_id": solar_system_id, "income": None},
                    )
                    moon.moonproduct_set.all().delete()
                    survey = survey[1:]
                    for product_data in survey:
                        # Trim off the empty index at the front
                        product_data = product_data[1:]
                        MoonProduct.objects.create(
                            moon=moon,
                            amount=product_data[1],
                            ore_type_id=product_data[2],
                        )
                    moon.income = moon.calc_income_estimate(
                        MOONPLANNER_VOLUME_PER_MONTH, MOONPLANNER_REPROCESSING_YIELD
                    )
                    moon.save()
                    logger.info("Added moon survey for %s", moon.name())

            except Exception as ex:
                logger.warning(
                    "An issue occurred while processing the following moon survey: "
                    f"{survey}",
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
    if user_pk:
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
            user=User.objects.get(pk=user_pk),
            title="Moon survey input processing results: {}".format(
                "OK" if success else "FAILED"
            ),
            message=message,
            level="success" if success else "danger",
        )

    return success


@shared_task
def run_refineries_update(mining_corp_pk, user_pk=None):
    """update list of refineries with extractions for a mining corporation"""

    addTag = make_logger_prefix("(none)")
    try:
        try:
            mining_corp = MiningCorporation.objects.get(pk=mining_corp_pk)
        except MiningCorporation.DoesNotExist as ex:
            raise MiningCorporation.DoesNotExist(
                "task called for non existing corp with pk {}".format(mining_corp_pk)
            )
            raise ex
        else:
            addTag = make_logger_prefix("update_refineries: {}".format(mining_corp))

        if mining_corp.character is None:
            logger.error(addTag("Missing character"))
            raise EveCharacter.DoesNotExist()

        token = mining_corp.fetch_token()
        logger.info(addTag("Using token from {}".format(mining_corp.character)))

        # get all corporation structures
        logger.info(addTag("Fetching corp structures"))

        all_structures = (
            esi.client.Corporation.get_corporations_corporation_id_structures(
                corporation_id=mining_corp.corporation.corporation_id,
                token=token.valid_access_token(),
            ).result()
        )

        logger.info(addTag("Updating refineries"))
        user_report = list()
        for refinery in all_structures:
            eve_type, _ = EveType.objects.get_or_create_esi(id=refinery["type_id"])
            if eve_type.eve_group_id == REFINERY_GROUP_ID:
                # determine moon next to refinery
                structure_info = (
                    esi.client.Universe.get_universe_structures_structure_id(
                        structure_id=refinery["structure_id"],
                        token=token.valid_access_token(),
                    ).result()
                )
                solar_system, _ = EveSolarSystem.objects.get_or_create_esi(
                    id=structure_info["solar_system_id"]
                )
                nearest_celestial = solar_system.nearest_celestial(
                    structure_info["position"]["x"],
                    structure_info["position"]["y"],
                    structure_info["position"]["z"],
                    group_id=MOON_GROUP_ID,
                    max_distance=MAX_DISTANCE_TO_MOON_METERS,
                )

                if nearest_celestial and nearest_celestial.eve_type.id == 14:
                    eve_moon = nearest_celestial.eve_object
                    eve_type, _ = EveType.objects.get_or_create_esi(
                        id=structure_info["type_id"]
                    )
                    refinery, _ = Refinery.objects.update_or_create(
                        structure_id=refinery["structure_id"],
                        defaults={
                            "name": structure_info["name"],
                            "eve_type": eve_type,
                            "eve_moon": eve_moon,
                            "corporation": mining_corp,
                        },
                    )
                    user_report.append(
                        {"moon_name": eve_moon.name, "refinery_name": refinery.name}
                    )

        # fetch notifications
        logger.info(addTag("Fetching notifications"))
        notifications = esi.client.Character.get_characters_character_id_notifications(
            character_id=mining_corp.character.character_id,
            token=token.valid_access_token(),
        ).result()

        # add extractions for refineries if any are found
        logger.info(
            addTag(
                "Process extraction events from {} notifications".format(
                    len(notifications)
                )
            )
        )
        with transaction.atomic():
            last_extraction_started = dict()
            for notification in sorted(notifications, key=lambda k: k["timestamp"]):
                if notification["type"] == "MoonminingExtractionStarted":
                    parsed_text = yaml.safe_load(notification["text"])
                    structure_id = parsed_text["structureID"]
                    refinery = Refinery.objects.get(structure_id=structure_id)
                    extraction, _ = Extraction.objects.get_or_create(
                        refinery=refinery,
                        ready_time=ldap_time_2_datetime(parsed_text["readyTime"]),
                        defaults={
                            "auto_time": ldap_time_2_datetime(parsed_text["autoTime"])
                        },
                    )
                    last_extraction_started[structure_id] = extraction
                    ore_volume_by_type = parsed_text["oreVolumeByType"].items()
                    for ore_type_id, ore_volume in ore_volume_by_type:
                        eve_type, _ = EveType.objects.get_or_create_esi(id=ore_type_id)
                        ExtractionProduct.objects.get_or_create(
                            extraction=extraction,
                            eve_type=eve_type,
                            defaults={"volume": ore_volume},
                        )

                # remove latest started extraction if it was canceled
                # and not finished
                if notification["type"] == "MoonminingExtractionCancelled":
                    parsed_text = yaml.safe_load(notification["text"])
                    structure_id = parsed_text["structureID"]
                    if structure_id in last_extraction_started:
                        extraction = last_extraction_started[structure_id]
                        extraction.delete()

                if notification["type"] == "MoonminingExtractionFinished":
                    parsed_text = yaml.safe_load(notification["text"])
                    structure_id = parsed_text["structureID"]
                    if structure_id in last_extraction_started:
                        del last_extraction_started[structure_id]

    except Exception as ex:
        logger.error(addTag("An unexpected error occurred: {}".format(ex)))
        success = False
        raise ex
    else:
        success = True

    if user_pk:
        message = (
            "The following refineries from {} have been added "
            "or updated:\n\n".format(mining_corp)
        )
        for report in user_report:
            message += "{} @ {}\n".format(
                report["moon_name"],
                report["refinery_name"],
            )

        notify(
            user=User.objects.get(pk=user_pk),
            title="Adding refinery report: {}".format("OK" if success else "FAILED"),
            message=message,
            level="success" if success else "danger",
        )


@shared_task
def update_moon_income():
    """update the income for all moons"""
    try:
        logger.info("Starting ESI client...")
        logger.info("Fetching market prices from ESI...")
        market_data = esi.client.Market.get_markets_prices().result()
        logger.info("Storing market prices...")
        for row in market_data:
            average_price = row["average_price"] if "average_price" in row else None
            adjusted_price = row["adjusted_price"] if "adjusted_price" in row else None
            try:
                EveMarketPrice.objects.update_or_create(
                    type_id=row["type_id"],
                    defaults={
                        "average_price": average_price,
                        "adjusted_price": adjusted_price,
                    },
                )
            except IntegrityError as error:
                # ignore rows which no matching evetype in the DB
                logger.info(
                    "failed to add row for type ID {} due to "
                    "IntegrityError: {}".format(row["type_id"], error)
                )

        logger.info(
            "Started re-calculating moon income for {:,} moons".format(
                MoonIncome.objects.count()
            )
        )
        with transaction.atomic():
            for moon in MoonIncome.objects.all():
                moon.income = moon.calc_income_estimate(
                    MOONPLANNER_VOLUME_PER_MONTH, MOONPLANNER_REPROCESSING_YIELD
                )
                moon.save()
        logger.info("Completed re-calculating moon income")

    except Exception as ex:
        logger.error("An unexpected error occurred: {}".format(ex))
