from celery import chain, shared_task

from django.contrib.auth.models import User
from eveuniverse.models import EveMarketPrice

from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag

from . import __title__
from .models import MiningCorporation, Moon

logger = LoggerAddTag(get_extension_logger(__name__), __title__)


@shared_task
def process_survey_input(scans, user_pk=None) -> bool:
    """Update moons from survey input."""
    user = User.objects.get(pk=user_pk) if user_pk else None
    return Moon.objects.update_moons_from_survey(scans, user)


@shared_task
def update_all_mining_corporations():
    mining_corporation_pks = MiningCorporation.objects.values_list("pk", flat=True)
    logger.info("Updating %d mining corporations...", len(mining_corporation_pks))
    for corporation_pk in mining_corporation_pks:
        update_mining_corporation.delay(corporation_pk)


@shared_task
def update_mining_corporation(corporation_pk):
    """update refineries and extractions from a mining corporation"""
    chain(
        update_refineries_from_esi.si(corporation_pk),
        update_extractions_from_esi.si(corporation_pk),
    ).delay()


@shared_task
def update_refineries_from_esi(corporation_pk):
    """update refineries for a mining corporation from ESI"""
    mining_corp = MiningCorporation.objects.get(pk=corporation_pk)
    mining_corp.update_refineries_from_esi()


@shared_task
def update_extractions_from_esi(corporation_pk):
    """update extractions for a mining corporation from ESI"""
    mining_corp = MiningCorporation.objects.get(pk=corporation_pk)
    mining_corp.update_extractions_from_esi()


@shared_task
def update_all_moon_income():
    """update the income for all moons"""
    moon_pks = Moon.objects.values_list("pk", flat=True)
    logger.info("Updating moon income for %d moons...", len(moon_pks))
    EveMarketPrice.objects.update_from_esi()
    for moon_pk in moon_pks:
        update_moon_income.delay(moon_pk)


@shared_task
def update_moon_income(moon_pk):
    moon = Moon.objects.get(pk=moon_pk)
    moon.update_income_estimate()
