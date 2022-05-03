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
import datetime as dt
import json
import random
from pathlib import Path

from django.contrib.auth.models import User
from django.utils.timezone import now
from eveuniverse.models import EveEntity, EveMarketPrice, EveMoon, EveType

from allianceauth.eveonline.models import EveCorporationInfo

from moonmining.app_settings import MOONMINING_VOLUME_PER_MONTH
from moonmining.models import (
    EveOreType,
    Extraction,
    ExtractionProduct,
    MiningLedgerRecord,
    Moon,
    MoonProduct,
    Owner,
    Refinery,
)

MAX_MOONS = 5
MAX_REFINERIES = 2
MAX_MINERS = 3
MAX_MINING_MONTHS = 3
MAX_MINING_ALTS_PER_MINER = 3
MAX_MINING_DAYS = 10
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


def generate_extraction(refinery, chunk_arrival_at, started_by, status):
    extraction = Extraction.objects.create(
        refinery=refinery,
        chunk_arrival_at=chunk_arrival_at,
        auto_fracture_at=chunk_arrival_at + dt.timedelta(hours=4),
        started_by=started_by,
        started_at=chunk_arrival_at - dt.timedelta(days=14),
        status=status,
    )
    for product in moon.products.all():
        ExtractionProduct.objects.create(
            extraction=extraction,
            ore_type=product.ore_type,
            volume=MOONMINING_VOLUME_PER_MONTH * product.amount,
        )
    return extraction


data_path = Path(__file__).parent / "generate_moons.json"
with data_path.open("r", encoding="utf-8") as fp:
    data = json.load(fp)
moon_ids = [int(obj["moon_id"]) for obj in data["moons"]]
ore_type_ids = [int(obj["type_id"]) for obj in data["ore_type_ids"]]

print(f"Generating {MAX_MOONS} moons...")
random_user = User.objects.order_by("?").first()
my_moons = list()
for moon_id in random.sample(moon_ids, k=MAX_MOONS):
    print(f"Creating moon {moon_id}")
    eve_moon, _ = EveMoon.objects.get_or_create_esi(id=moon_id)
    moon, created = Moon.objects.get_or_create(
        eve_moon=eve_moon,
        defaults={
            "products_updated_at": now(),
            "products_updated_by": random_user,
        },
    )
    my_moons.append(moon)
    if created:
        percentages = random_percentages(4)
        for ore_type_id in random.sample(ore_type_ids, k=4):
            ore_type, _ = EveOreType.objects.get_or_create_esi(id=ore_type_id)
            MoonProduct.objects.create(
                moon=moon, ore_type=ore_type, amount=percentages.pop()
            )
        moon.update_calculated_properties()
print(f"Generating {MAX_REFINERIES} refineries...")
try:
    corporation = EveCorporationInfo.objects.get(corporation_id=DUMMY_CORPORATION_ID)
except EveCorporationInfo.DoesNotExist:
    corporation = EveCorporationInfo.objects.create_corporation(
        corp_id=DUMMY_CORPORATION_ID
    )
owner, _ = Owner.objects.get_or_create(corporation=corporation)
Refinery.objects.filter(owner=owner).delete()
eve_type, _ = EveType.objects.get_or_create_esi(id=35835)
character, _ = EveEntity.objects.get_or_create_esi(id=DUMMY_CHARACTER_ID)
my_extractions = list()
for moon in random.choices(my_moons, k=MAX_REFINERIES):
    if not hasattr(moon, "refinery"):
        print(f"Creating refinery for moon: {moon}")
        refinery = Refinery.objects.create(
            id=moon.eve_moon.id,
            name=f"Test Refinery #{moon.eve_moon.id}",
            moon=moon,
            owner=owner,
            eve_type=eve_type,
        )
        my_extractions.append(
            generate_extraction(
                refinery=refinery,
                chunk_arrival_at=now() + dt.timedelta(days=random.randint(7, 30)),
                started_by=character,
                status=Extraction.Status.STARTED,
            )
        )
        my_extractions.append(
            generate_extraction(
                refinery=refinery,
                chunk_arrival_at=now() - dt.timedelta(days=random.randint(7, 30)),
                started_by=character,
                status=Extraction.Status.CANCELED,
            )
        )
        my_extractions.append(
            generate_extraction(
                refinery=refinery,
                chunk_arrival_at=now() - dt.timedelta(days=random.randint(7, 30)),
                started_by=character,
                status=Extraction.Status.COMPLETED,
            )
        )
print(f"Generating mining ledger...")

for refinery in Refinery.objects.select_related("owner__corporation").filter(
    owner__corporation__corporation_id=DUMMY_CORPORATION_ID
):
    for user in User.objects.order_by("?"):
        for character_ownership in user.character_ownerships.select_related(
            "character"
        ).all()[:MAX_MINING_ALTS_PER_MINER]:
            character, _ = EveEntity.objects.get_or_create_esi(
                id=character_ownership.character.character_id
            )
            corporation, _ = EveEntity.objects.get_or_create_esi(
                id=character_ownership.character.corporation_id
            )
            all_days = sorted([now() - dt.timedelta(days=day) for day in range(31 * 4)])
            for day in random.sample(all_days, k=MAX_MINING_DAYS):
                for ore_type_id in refinery.moon.products.values_list(
                    "ore_type_id", flat=True
                ):
                    MiningLedgerRecord.objects.create(
                        refinery=refinery,
                        day=day,
                        character=character,
                        ore_type_id=ore_type_id,
                        corporation=corporation,
                        quantity=random.randint(10000, 100000),
                        user=user,
                    )


print(f"Updating calculated properties...")
EveMarketPrice.objects.update_from_esi()
for moon in my_moons:
    moon.update_calculated_properties()
for extraction in my_extractions:
    extraction.update_calculated_properties()
print("DONE")
