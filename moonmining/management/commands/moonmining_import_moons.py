import csv
from concurrent import futures
from functools import partial
from pathlib import Path

from bravado.exception import HTTPBadGateway, HTTPGatewayTimeout, HTTPServiceUnavailable

from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction
from eveuniverse.core.esitools import is_esi_online
from eveuniverse.models import EveMoon

from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag

from moonmining.models import EveOreType, Moon, MoonProduct

from ... import __title__

MAX_RETRIES = 3
BULK_BATCH_SIZE = 500
MAX_THREAD_WORKERS = 20


logger = LoggerAddTag(get_extension_logger(__name__), __title__)


class Command(BaseCommand):
    help = "Import moons from an CSV file."

    def add_arguments(self, parser):
        parser.add_argument("input_file", help="Path of CSV file to be imported")
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

    def handle(self, *args, **options):
        if not options["disable_esi_check"] and not is_esi_online():
            raise CommandError("ESI if offline. Aborting")

        input_file = Path(options["input_file"])
        if not input_file.exists():
            raise CommandError(
                f"Could not find a file with the path: {input_file.resolve()}"
            )
        moons, ore_types = self._read_moons(input_file)
        self._fetch_missing_eve_objects(
            EveModel=EveMoon,
            ids_incoming=set(moons.keys()),
            force_refetch=options["force_refetch"],
        )
        self._fetch_missing_eve_objects(
            EveModel=EveOreType,
            ids_incoming=ore_types,
            force_refetch=options["force_refetch"],
        )
        self._create_moons(moons, options["force_update"])
        self.stdout.write(self.style.SUCCESS("Done."))

    def _read_moons(self, input_file) -> tuple:
        self.stdout.write(f"Importing moons from: {input_file} ...")
        moons = dict()
        ore_types = set()
        with input_file.open("r", encoding="utf-8") as fp:
            csv_reader = csv.DictReader(fp)
            for row in csv_reader:
                moon_id = int(row["moon_id"])
                ore_type_id = int(row["ore_type_id"])
                amount = float(row["amount"])
                if moon_id not in moons:
                    moons[moon_id] = list()
                moons[moon_id].append((ore_type_id, amount))
                ore_types.add(ore_type_id)

        if not len(moons.keys()):
            raise CommandError("Import file contains no moons.")

        self.stdout.write(
            f"Input file contains {len(moons.keys())} moons.",
        )
        return moons, ore_types

    def _fetch_missing_eve_objects(
        self, EveModel: type, ids_incoming: set, force_refetch: bool
    ):
        if force_refetch:
            ids_to_fetch = set(ids_incoming)
        else:
            ids_existing = set(EveModel.objects.values_list("id", flat=True))
            ids_to_fetch = set(ids_incoming) - ids_existing
        if not len(ids_to_fetch):
            self.stdout.write(f"No {EveModel.__name__} objects to fetch from ESI")
            return
        self.stdout.write(
            f"Fetching {len(ids_to_fetch)} {EveModel.__name__} objects from ESI..."
        )
        with futures.ThreadPoolExecutor(max_workers=MAX_THREAD_WORKERS) as executor:
            executor.map(
                partial(self._thread_fetch_eve_object, EveModel), list(ids_to_fetch)
            )
        ids_existing = set(EveModel.objects.values_list("id", flat=True))
        ids_missing = ids_to_fetch - ids_existing
        if ids_missing:
            logger.debug(
                "%s: Missing %d ids: %s",
                EveModel.__name__,
                len(ids_missing),
                ids_missing,
            )
            raise CommandError(
                f"Failed to fetch all {EveModel.__name__} objects. Please try again"
            )

    @staticmethod
    def _thread_fetch_eve_object(EveModel: type, id: int):
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
            except (
                HTTPBadGateway,
                HTTPGatewayTimeout,
                HTTPServiceUnavailable,
                IntegrityError,
            ) as ex:
                logger.exception("Recoverable error occurred: %s", ex)
            else:
                break

    @transaction.atomic()
    def _create_moons(self, moons, force_update):
        ids_incoming = set(moons.keys())
        ids_existing = set(Moon.objects.values_list("pk", flat=True))
        ids_missing = ids_incoming - ids_existing
        new_moons = {
            moon_id: moon for moon_id, moon in moons.items() if moon_id in ids_missing
        }
        if not len(new_moons):
            self.stdout.write("No Moon objects to create")
        else:
            self.stdout.write(
                f"Writing {len(new_moons)} Moon objects...",
            )
            moon_objects = [Moon(eve_moon_id=moon_id) for moon_id in new_moons.keys()]
            Moon.objects.bulk_create(moon_objects, batch_size=BULK_BATCH_SIZE)

        if force_update:
            Moon.objects.filter(pk__in=ids_existing).update(
                products_updated_at=None, products_updated_by=None
            )
            MoonProduct.objects.filter(moon__pk__in=moons.keys()).delete()
            product_moons = moons
        else:
            product_moons = new_moons

        # create moon products
        if not len(product_moons):
            self.stdout.write("No MoonProduct objects to create")
        else:
            self.stdout.write(
                f"Writing approx. {len(product_moons) * 3.5:,.0f} " "moon products..."
            )
            product_objects = []
            for moon_id, moon_data in product_moons.items():
                for ore in moon_data:
                    product_objects.append(
                        MoonProduct(moon_id=moon_id, ore_type_id=ore[0], amount=ore[1])
                    )
            MoonProduct.objects.bulk_create(product_objects, batch_size=BULK_BATCH_SIZE)
