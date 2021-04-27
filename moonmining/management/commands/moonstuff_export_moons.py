import csv
import datetime as dt
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from app_utils.django import app_labels


class Command(BaseCommand):
    help = "Export moons from moonstuff v1 to a CSV file."

    def add_arguments(self, parser):
        parser.add_argument(
            "path",
            nargs="?",
            default=Path.cwd(),
            help="Path to create exported CSV file in, e.g. /home/johndoe/export",
        )

    def handle(self, *args, **options):
        if "moonstuff" not in app_labels():
            raise CommandError("Moonstuff does not seam to be installed. Aborting.")

        from moonstuff import __version__
        from moonstuff.models import Moon, Resource

        if int(__version__.split(".")[0]) != 1:
            raise CommandError(
                "Sorry, but this export tool only works with Moonstuff v1"
            )

        today_str = dt.datetime.now().strftime("%Y%m%d")
        my_file = Path(options["path"]) / f"moonstuff_export_{today_str}.csv"
        moons_count = Moon.objects.count()
        self.stdout.write(f"Exporting {moons_count} moons to: {my_file} ...")
        with my_file.open("w", encoding="utf-8") as fp:
            fieldnames = ["moon_id", "ore_type_id", "amount"]
            writer = csv.DictWriter(fp, fieldnames=fieldnames)
            writer.writeheader()
            for resource in Resource.objects.select_related("ore_id").all():
                for moon in resource.moon_set.all():
                    writer.writerow(
                        {
                            "moon_id": moon.moon_id,
                            "ore_type_id": resource.ore_id.ore_id,
                            "amount": resource.amount,
                        }
                    )
        self.stdout.write(self.style.SUCCESS("Done."))
