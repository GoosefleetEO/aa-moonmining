# flake8: noqa
"""scripts generates moons for load testing

This script can be executed directly from shell.
"""

import os
import sys
from pathlib import Path

myauth_dir = Path(__file__).parent.parent.parent.parent.parent / "myauth"
sys.path.insert(0, str(myauth_dir))

import django
from django.apps import apps

# init and setup django project
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myauth.settings.local")
django.setup()

"""SCRIPT"""
import concurrent.futures
import csv
import random
from pathlib import Path

from django.contrib.auth.models import User
from django.utils.timezone import now
from eveuniverse.core.esitools import is_esi_online
from eveuniverse.models import EveMoon

from moonmining.models import EveOreType, Moon, MoonProduct
from moonmining.tests.testdata.factories import random_percentages

MAX_MOONS = 100

ORE_TYPES = {
    45490: "Zeolites",
    45491: "Sylvite",
    45492: "Bitumens",
    45493: "Coesite",
    45494: "Cobaltite",
    45495: "Euxenite",
    45496: "Titanite",
    45497: "Scheelite",
    45498: "Otavite",
    45499: "Sperrylite",
    45500: "Vanadinite",
    45501: "Chromite",
    45502: "Carnotite",
    45503: "Zircon",
    45504: "Pollucite",
    45506: "Cinnabar",
    45510: "Xenotime",
    45511: "Monazite",
    45512: "Loparite",
    45513: "Ytterbite",
}


def create_moon(moon_id):
    eve_moon, _ = EveMoon.objects.get_or_create_esi(id=moon_id)
    moon, created = Moon.objects.get_or_create(
        eve_moon=eve_moon,
        defaults={
            "products_updated_at": now(),
            "products_updated_by": random_user,
        },
    )
    if created:
        percentages = random_percentages(4)
        for ore_type_id in random.sample(ore_type_ids, k=4):
            ore_type, _ = EveOreType.objects.get_or_create_esi(id=ore_type_id)
            MoonProduct.objects.create(
                moon=moon, ore_type=ore_type, amount=percentages.pop()
            )
        moon.update_calculated_properties()


print(f"Generating {MAX_MOONS} moons...")
data_path = Path(__file__).parent / "moon_ids.csv"
with data_path.open("r", encoding="utf-8") as fp:
    csv_reader = csv.reader(fp)
    moon_ids = [int(obj[0]) for obj in list(csv_reader)]
ore_type_ids = list(ORE_TYPES.keys())
random_user = User.objects.order_by("?").first()

if not is_esi_online():
    print("ESI is offline - aborting")

with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
    executor.map(create_moon, random.sample(moon_ids, k=MAX_MOONS))

print()
print(f"{MAX_MOONS} moons generated.")
