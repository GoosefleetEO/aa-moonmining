import logging

from django.core.management.base import BaseCommand
from eveuniverse.models import EveCategory

from app_utils.logging import LoggerAddTag

from moonmining.models import EveOreType

from ... import __title__, constants
from . import get_input

logger = LoggerAddTag(logging.getLogger(__name__), __title__)


class Command(BaseCommand):
    help = "Preload all necessary types."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force-reload",
            action="store_true",
            help="Force reloading of all objects from ESI",
        )

    def handle(self, *args, **options):
        self.stdout.write("Preloading types for Moon Mining")
        self.stdout.write()
        user_input = get_input("Are you sure you want to proceed? (y/N)?")

        if user_input.lower() == "y":
            self.stdout.write("Loading ore category incl. related objects...")
            EveCategory.objects.get_or_create_esi(
                id=constants.EVE_CATEGORY_ID_ASTEROID, include_children=True
            )
            ore_type_ids = EveOreType.objects.filter(
                eve_group__eve_category_id=constants.EVE_CATEGORY_ID_ASTEROID
            ).values_list("id", flat=True)
            self.stdout.write(f"Loading {len(ore_type_ids)} ore types...")
            if not options["force_reload"]:
                for ore_type_id in ore_type_ids:
                    EveOreType.objects.get_or_create_esi(id=ore_type_id)
            else:
                self.stdout.write("Forced reload activated...")
                for ore_type_id in ore_type_ids:
                    EveOreType.objects.update_or_create_esi(id=ore_type_id)

            self.stdout.write(self.style.SUCCESS("Done"))
        else:
            self.stdout.write(self.style.WARNING("Aborted"))
