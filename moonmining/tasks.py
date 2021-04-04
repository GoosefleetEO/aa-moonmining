from celery import chain, shared_task

from django.contrib.auth.models import User
from django.utils.timezone import now
from eveuniverse.models import EveMarketPrice

from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag

from . import __title__
from .models import Extraction, Moon, Owner

logger = LoggerAddTag(get_extension_logger(__name__), __title__)

TASK_PRIORITY_LOWER = 6


@shared_task
def process_survey_input(scans, user_pk=None) -> bool:
    """Update moons from survey input."""
    user = User.objects.get(pk=user_pk) if user_pk else None
    return Moon.objects.update_moons_from_survey(scans, user)


@shared_task
def run_regular_updates():
    """Run main tasks for regular updates."""
    owners_to_update = Owner.objects.filter(is_enabled=True)
    owner_pks = owners_to_update.values_list("pk", flat=True)
    logger.info("Updating %d owners...", len(owner_pks))
    owners_to_update.update(last_update_ok=None, last_update_at=now())
    for owner_pk in owner_pks:
        update_owner.delay(owner_pk)


@shared_task
def update_owner(owner_pk):
    """Update refineries and extractions for given owner."""
    chain(
        update_refineries_from_esi_for_owner.si(owner_pk),
        fetch_notifications_from_esi_for_owner.si(owner_pk),
        update_extractions_for_owner.si(owner_pk),
        mark_successful_update_for_owner.si(owner_pk),
    ).delay()


@shared_task
def update_refineries_from_esi_for_owner(owner_pk):
    """Update refineries for a owner from ESI."""
    owner = Owner.objects.get(pk=owner_pk)
    owner.update_refineries_from_esi()


@shared_task
def fetch_notifications_from_esi_for_owner(owner_pk):
    """Update extractions for a owner from ESI."""
    owner = Owner.objects.get(pk=owner_pk)
    owner.fetch_notifications_from_esi()


@shared_task
def update_extractions_for_owner(owner_pk):
    """Update extractions for a owner from ESI."""
    owner = Owner.objects.get(pk=owner_pk)
    owner.update_extractions()


@shared_task
def mark_successful_update_for_owner(owner_pk):
    """Mark a successful update for this corporation."""
    owner = Owner.objects.get(pk=owner_pk)
    owner.last_update_ok = True
    owner.save()


@shared_task
def run_calculated_properties_update():
    """Update the calculated properties of all moons and all extractions."""
    EveMarketPrice.objects.update_from_esi()
    update_moons.delay()
    update_extractions.delay()


@shared_task
def update_moons():
    """Update the calculated properties of all moons."""
    moon_pks = Moon.objects.values_list("pk", flat=True)
    logger.info("Updating calculated properties for %d moons ...", len(moon_pks))
    for moon_pk in moon_pks:
        update_moon_calculated_properties.apply_async(
            kwargs={"moon_pk": moon_pk}, priority=TASK_PRIORITY_LOWER
        )


@shared_task
def update_extractions():
    """Update the calculated properties of all extractions."""
    extraction_pks = Extraction.objects.values_list("pk", flat=True)
    logger.info(
        "Updating calculated properties for %d extractions ...", len(extraction_pks)
    )
    for extraction_pk in extraction_pks:
        update_extraction_calculated_properties.apply_async(
            kwargs={"extraction_pk": extraction_pk}, priority=TASK_PRIORITY_LOWER
        )


@shared_task
def update_moon_calculated_properties(moon_pk):
    """Update all calculated properties for given moon."""
    moon = Moon.objects.get(pk=moon_pk)
    moon.update_calculated_properties()


@shared_task
def update_extraction_calculated_properties(extraction_pk):
    """Update all calculated properties for given extraction."""
    extraction = Extraction.objects.get(pk=extraction_pk)
    extraction.update_calculated_properties()