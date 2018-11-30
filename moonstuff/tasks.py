from .models import Resource, Moon
from celery import shared_task
import logging

logger = logging.getLogger(__name__)


@shared_task
def process_resources(scan):
    """
    This function processes a moonscan and saves the resources.

    Example Scan:
                  [
                    ['Moon Name', '', '', '', '', '', ''],
                    ['','Resource Name','Decimal Percentage','Resource Type ID','Solar System ID','Planet ID','Moon ID'],
                    ['...'],
                  ]
    :param scan: list
    :return: None
    """
    try:
        moon_name = scan[0][0]
        system_id = scan[1][3]
        moon_id = scan[1][5]
        moon, _ = Moon.objects.get_or_create(name=moon_name, system_id=system_id, moon_id=moon_id)
        scan = scan[1:]
        for res in scan:
            # Trim off the empty index at the front
            res = res[1:]

            # While extremely unlikely, it is possible that 2 moons might have the same percentage
            # of an ore in them, so we will account for this.
            resource, _ = Resource.objects.get_or_create(ore=res[0], amount=res[1], ore_id=res[2])
            moon.resources.add(resource.pk)
    except Exception as e:
        logger.error("An Error occurred while processing the following moon scan. {}".format(scan))
        logger.error(e)
    return

