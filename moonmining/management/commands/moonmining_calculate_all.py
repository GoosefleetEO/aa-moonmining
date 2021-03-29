import logging

from django.core.management.base import BaseCommand

from app_utils.logging import LoggerAddTag

from moonmining.models import Extraction, Moon

from ... import __title__
from . import get_input

logger = LoggerAddTag(logging.getLogger(__name__), __title__)


class Command(BaseCommand):
    help = "Calculate all properties for moons and extractions."

    def handle(self, *args, **options):
        moon_count = Moon.objects.count()
        extractions_count = Extraction.objects.count()
        self.stdout.write(
            f"Updating calculated properties for {moon_count} moons "
            f"and {extractions_count} extractions. This can take a while."
        )
        self.stdout.write()
        user_input = get_input("Are you sure you want to proceed? (y/N)?")

        if user_input.lower() == "y":
            for MyModel in [Moon, Extraction]:
                obj_count = MyModel.objects.count()
                self.stdout.write(
                    f"Updating calculated properties for {obj_count} "
                    f"{MyModel.__name__}s ..."
                )
                MyModel.objects.all().update_calculated_properties()

            self.stdout.write(self.style.SUCCESS("Done"))
        else:
            self.stdout.write(self.style.WARNING("Aborted"))
