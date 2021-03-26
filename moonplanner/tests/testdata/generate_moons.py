# flake8: noqa
"""scripts generates large amount of moons for load testing

This script can be executed directly from shell.

SQLs:

SELECT itemID as moon_id
FROM eve_sde.mapDenormalize
WHERE typeID = 14 and regionID IN (10000069);

SELECT typeID
from eve_sde.invTypes
join eve_sde.invGroups on eve_sde.invTypes.groupID = eve_sde.invGroups.groupID
where categoryID = 25 and eve_sde.invTypes.published is TRUE and eve_sde.invGroups.published IS TRUE
and eve_sde.invTypes.portionSize = 100 and mass = 4000 and volume = 10
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
import datetime as dt
import json
import random
from pathlib import Path

from django.contrib.auth.models import User
from django.utils.timezone import now
from eveuniverse.models import EveEntity, EveMoon, EveType

from allianceauth.eveonline.models import EveCorporationInfo

from moonplanner.app_settings import MOONPLANNER_VOLUME_PER_MONTH
from moonplanner.models import (
    EveOreType,
    Extraction,
    ExtractionProduct,
    MiningCorporation,
    Moon,
    MoonProduct,
    Refinery,
)

MAX_MOONS = 5
MAX_REFINERIES = 2
DUMMY_CORPORATION_ID = 1000127  # Guristas
DUMMY_CHARACTER_ID = 3019491  # Guristas CEO


def random_percentages(parts) -> list:
    percentages = []
    total = 0
    for _ in range(parts - 1):
        part = random.randint(0, 100 - total)
        percentages.append(part)
        total += part
    percentages.append(100 - total)
    return percentages


def generate_extraction(refinery, ready_time, started_by):
    extraction = Extraction.objects.create(
        refinery=refinery,
        ready_time=ready_time,
        auto_time=ready_time + dt.timedelta(hours=4),
        started_by=started_by,
    )
    for product in moon.products.all():
        ExtractionProduct.objects.create(
            extraction=extraction,
            ore_type=product.ore_type,
            volume=MOONPLANNER_VOLUME_PER_MONTH * product.amount,
        )


data_path = Path(__file__).parent / "generate_moons.json"
with data_path.open("r", encoding="utf-8") as fp:
    data = json.load(fp)
moon_ids = [int(obj["moon_id"]) for obj in data["moons"]]
ore_type_ids = [int(obj["type_id"]) for obj in data["ore_type_ids"]]

print(f"Generating {MAX_MOONS} moons...")
random_user = User.objects.order_by("?").first()
for moon_id in random.choices(moon_ids, k=MAX_MOONS):
    print(f"Creating moon {moon_id}")
    eve_moon, _ = EveMoon.objects.get_or_create_esi(id=moon_id)
    moon, created = Moon.objects.get_or_create(
        eve_moon=eve_moon,
        defaults={
            "value": random.randint(100000000, 10000000000),
            "products_updated_at": now(),
            "products_updated_by": random_user,
        },
    )
    if created:
        percentages = random_percentages(4)
        for ore_type_id in random.choices(ore_type_ids, k=4):
            ore_type, _ = EveOreType.objects.get_or_create_esi(id=ore_type_id)
            MoonProduct.objects.create(
                moon=moon, ore_type=ore_type, amount=percentages.pop() / 100
            )
print(f"Generating {MAX_REFINERIES} refineries...")
try:
    eve_corporation = EveCorporationInfo.objects.get(
        corporation_id=DUMMY_CORPORATION_ID
    )
except EveCorporationInfo.DoesNotExist:
    eve_corporation = EveCorporationInfo.objects.create_corporation(
        corp_id=DUMMY_CORPORATION_ID
    )
corporation, _ = MiningCorporation.objects.get_or_create(
    eve_corporation=eve_corporation
)
Refinery.objects.filter(corporation=corporation).delete()
eve_type, _ = EveType.objects.get_or_create_esi(id=35835)
character, _ = EveEntity.objects.get_or_create_esi(id=DUMMY_CHARACTER_ID)
for moon in Moon.objects.order_by("?")[:MAX_REFINERIES]:
    if not hasattr(moon, "refinery"):
        print(f"Creating refinery for moon: {moon}")
        refinery = Refinery.objects.create(
            id=moon.eve_moon.id,
            name=f"Test Refinery #{moon.eve_moon.id}",
            moon=moon,
            corporation=corporation,
            eve_type=eve_type,
        )
        generate_extraction(
            refinery=refinery,
            ready_time=now() + dt.timedelta(days=random.randint(7, 30)),
            started_by=character,
        )
        generate_extraction(
            refinery=refinery,
            ready_time=now() + dt.timedelta(days=-random.randint(7, 30)),
            started_by=character,
        )
        generate_extraction(
            refinery=refinery,
            ready_time=now() + dt.timedelta(days=-random.randint(7, 30)),
            started_by=character,
        )

print("DONE")
