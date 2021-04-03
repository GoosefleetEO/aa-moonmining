from django.core.management.base import BaseCommand
from eveuniverse.models import EveType
from eveuniverse.tasks import update_or_create_eve_object

from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag

from ... import __title__, constants
from ...models import EveOreType
from . import get_input

logger = LoggerAddTag(get_extension_logger(__name__), __title__)


class Command(BaseCommand):
    help = "Preloads data like ore types from ESI."

    def handle(self, *args, **options):
        self.stdout.write("Loading all ore types from ESI. This can take a while.")
        ore_types_count = EveOreType.objects.count()
        self.stdout.write(
            f"You currently have {ore_types_count} ore types in your database."
        )
        self.stdout.write()
        user_input = get_input("Are you sure you want to proceed? (y/N)?")

        if user_input.lower() == "y":
            self.stdout.write("Tasks for loading ore types have been started.")
            update_or_create_eve_object.delay(
                model_name="EveCategory",
                id=constants.EVE_CATEGORY_ID_ASTEROID,
                include_children=True,
                enabled_sections=[
                    EveType.Section.DOGMAS,
                    EveType.Section.TYPE_MATERIALS,
                ],
            )
            self.stdout.write(self.style.SUCCESS("Done"))
        else:
            self.stdout.write(self.style.WARNING("Aborted"))
