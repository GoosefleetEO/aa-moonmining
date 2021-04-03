# flake8: noqa
import argparse
import os
import sys
from pathlib import Path

parser = argparse.ArgumentParser(
    description=("This program imports moons from a CSV file into Moonplanner")
)
parser.add_argument(
    "input_file",
    help="name of CSV file in the current working directory to be imported",
)
parser.add_argument(
    "-a",
    "--path-to-myauth",
    help="REQUIRED: path to myauth root folder (where manage.py is located)",
    required=True,
)
parser.add_argument(
    "--force-refetch",
    action="store_const",
    const=True,
    default=False,
    help="When set all needed eveuniverse objects will be fetched again from ESI",
)
parser.add_argument(
    "--force-update",
    action="store_const",
    const=True,
    default=False,
    help="When set all Moon and MoonProduct objects will be updated from the input file",
)
parser.add_argument(
    "--force-calc",
    action="store_const",
    const=True,
    default=False,
    help="When set will always re-calculate income",
)
parser.add_argument(
    "--disable-esi-check",
    action="store_const",
    const=False,
    default=False,
    help="When set script will not check if ESI is online",
)
args = parser.parse_args()
myauth_path = Path(args.path_to_myauth)
if not (myauth_path / "manage.py").exists():
    print(f"Could not find manage.py in {myauth_path}")
    exit(1)
sys.path.insert(0, str(myauth_path))

import django

# init and setup django project
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myauth.settings.local")
django.setup()

"""MAIN SCRIPT STARTS HERE"""
import csv
import logging
from concurrent import futures
from functools import partial
from pathlib import Path

from bravado.exception import HTTPBadGateway, HTTPGatewayTimeout, HTTPServiceUnavailable

from django.db import transaction
from eveuniverse.core.esitools import is_esi_online
from eveuniverse.models import EveMoon

from moonmining.models import EveOreType, Moon, MoonProduct

MAX_RETRIES = 3
BULK_BATCH_SIZE = 500
MAX_THREAD_WORKERS = 20

logging.basicConfig(
    format="%(levelname)s: %(message)s", level=logging.DEBUG, datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)


def thread_fetch_eve_object(EveModel: type, id: int):
    for run in range(MAX_RETRIES + 1):
        try:
            with transaction.atomic():
                logger.info(
                    "Fetching %s object with id %s from ESI... %s",
                    EveModel.__name__,
                    id,
                    f"(retry #{run + 1})" if run > 0 else "",
                )
                EveModel.objects.update_or_create_esi(id=id)
        except (HTTPBadGateway, HTTPGatewayTimeout, HTTPServiceUnavailable) as ex:
            logger.exception("Recoverable HTTP error occurred: %s", ex)
        else:
            break


def fetch_missing_eve_objects(EveModel: type, ids_incoming: set, force_refetch: bool):
    if force_refetch:
        ids_to_fetch = set(ids_incoming)
    else:
        ids_existing = set(EveModel.objects.values_list("id", flat=True))
        ids_to_fetch = set(ids_incoming) - ids_existing
    if not len(ids_to_fetch):
        logger.info("No %s objects to fetch from ESI", EveModel.__name__)
        return
    logger.info(
        "Fetching %d %s objects from ESI...", len(ids_to_fetch), EveModel.__name__
    )
    with futures.ThreadPoolExecutor(max_workers=MAX_THREAD_WORKERS) as executor:
        executor.map(partial(thread_fetch_eve_object, EveModel), list(ids_to_fetch))
    ids_existing = set(EveModel.objects.values_list("id", flat=True))
    ids_missing = ids_to_fetch - ids_existing
    if ids_missing:
        logger.debug(
            "%s: Missing %d ids: %s", EveModel.__name__, len(ids_missing), ids_missing
        )
        logger.error(
            "Failed to fetch all %s objects. Please try again", EveModel.__name__
        )
        exit(1)


def main():
    if not args.disable_esi_check and not is_esi_online():
        logger.error("ESI if offline. Aborting")

    input_file = Path().cwd() / args.input_file
    logger.info("Importing moons from: %s ...", input_file)

    # fetch all data from file
    moons = dict()
    ore_types = set()
    with input_file.open("r", encoding="utf-8") as fp:
        csv_reader = csv.DictReader(fp)
        for row in csv_reader:
            moon_id = int(row["moon_id"])
            ore_type_id = int(row["ore_type_id"])
            amount = float(row["amount"])
            if not moon_id in moons:
                moons[moon_id] = list()
            moons[moon_id].append((ore_type_id, amount))
            ore_types.add(ore_type_id)

    logger.info("Input file contains %d moons.", len(moons.keys()))

    # fetch missing eve objects from ESI
    fetch_missing_eve_objects(
        EveModel=EveMoon,
        ids_incoming=set(moons.keys()),
        force_refetch=args.force_refetch,
    )
    fetch_missing_eve_objects(
        EveModel=EveOreType, ids_incoming=ore_types, force_refetch=args.force_refetch
    )

    # create moons
    with transaction.atomic():
        ids_incoming = set(moons.keys())
        ids_existing = set(Moon.objects.values_list("pk", flat=True))
        ids_missing = ids_incoming - ids_existing
        new_moons = {
            moon_id: moon for moon_id, moon in moons.items() if moon_id in ids_missing
        }
        if not len(new_moons):
            logger.info("No Moon objects to create")
        else:
            logger.info("Writing %d Moon objects...", len(new_moons))
            moon_objects = [Moon(eve_moon_id=moon_id) for moon_id in new_moons.keys()]
            Moon.objects.bulk_create(moon_objects, batch_size=BULK_BATCH_SIZE)

        if args.force_update:
            Moon.objects.filter(pk__in=ids_existing).update(
                products_updated_at=None, products_updated_by=None
            )
            MoonProduct.objects.filter(moon__pk__in=moons.keys()).delete()
            product_moons = moons
        else:
            product_moons = new_moons

        # create moon products
        if not len(product_moons):
            logger.info("No MoonProduct objects to create")
        else:
            logger.info(
                "Writing approx. %d MoonProduct objects...", len(product_moons) * 3.5
            )
            product_objects = []
            for moon_id, moon_data in product_moons.items():
                for ore in moon_data:
                    product_objects.append(
                        MoonProduct(moon_id=moon_id, ore_type_id=ore[0], amount=ore[1])
                    )
            MoonProduct.objects.bulk_create(product_objects, batch_size=BULK_BATCH_SIZE)

    # updated_moon_ids = (
    #     moons.keys() if args.force_update or args.force_calc else new_moons.keys()
    # )
    # if updated_moon_ids:
    #     logger.info(
    #         "Updating calculated properties for %d moons...", len(updated_moon_ids)
    #     )
    #     Moon.objects.filter(pk__in=updated_moon_ids).update_calculated_properties()

    logger.info("DONE")


main()
