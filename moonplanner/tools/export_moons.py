# flake8: noqa
import argparse
import os
import sys
from pathlib import Path

parser = argparse.ArgumentParser(
    description=(
        "This program exports all moons of Moonplanner into a CSV file "
        "in the current working directory"
    )
)
parser.add_argument(
    "-a",
    "--path-to-myauth",
    help="REQUIRED: path to myauth root folder (where manage.py is located)",
    required=True,
)
args = parser.parse_args()
myauth_path = Path(args.path_to_myauth)
if not (myauth_path / "manage.py").exists():
    print(f"Could not find manage.py in {myauth_path}")
    exit(1)
sys.path.insert(0, str(myauth_path))

import django
from django.apps import apps

# init and setup django project
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myauth.settings.local")
django.setup()

"""MAIN SCRIPT STARTS HERE"""
import csv
import datetime as dt
from pathlib import Path

from moonplanner.models import Moon, MoonProduct

now_text = dt.datetime.utcnow().strftime("%Y%m%d")
output_file = Path().cwd() / f"moonplanner_export_moons_{now_text}.csv"
print(f"Exporting {Moon.objects.count()} moons ...")
print(f"File: {output_file}...")
with output_file.open("w", encoding="utf-8") as fp:
    csv_writer = csv.writer(fp)
    csv_writer.writerow(["moon_id", "ore_type_id", "amount"])
    for product in MoonProduct.objects.order_by("moon_id"):
        csv_writer.writerow([product.moon_id, product.ore_type_id, product.amount])
print("DONE")
