from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from esi.decorators import token_required
import os
import datetime
from allianceauth.eveonline.models import EveCorporationInfo
from .models import *

SWAGGER_SPEC_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'swagger.json')
"""
Swagger Operations:
get_characters_character_id
get_universe_structures_structure_id
get_universe_moons_moon_id
get_corporation_corporation_id
get_corporation_corporation_id_mining_extractions
"""


# Create your views here.
@login_required
def moon_index(request):
    ctx = {}
    return render(request, 'moonstuff/moon_index.html', ctx)


@token_required(scopes=['esi-industry.read_corporation_mining.v1', 'esi-universe.read_structures.v1'])
@login_required
def import_data(request, token):
    ctx = {}
    c = token.get_esi_client(spec_file=SWAGGER_SPEC_FILE)
    try:
        char = c.Character.get_characters_character_id(character_id=token.character_id).result()
        corp_id = char['corporation_id']
        e = c.Industry.get_corporation_corporation_id_mining_extractions(corporation_id=corp_id).result()
        for event in e:
            # Gather structure information.
            print(event)
            try:
                moon = Moon.objects.get(moon_id=event['moon_id'])
            except models.ObjectDoesNotExist:
                # Moon Info
                m = c.Universe.get_universe_moons_moon_id(moon_id=event['moon_id']).result()
                moon, created = Moon.objects.get_or_create(moon_id=event['moon_id'], system_id=m['system_id'], name=m['name'])

            try:
                ref = Refinery.objects.get(structure_id=event['structure_id'])
            except models.ObjectDoesNotExist:
                r = c.Universe.get_universe_structures_structure_id(structure_id=event['structure_id']).result()
                refName = r['name']
                owner = r['owner_id']
                # TypeIDs: Athanor - 35835 | Tatara - 35836
                size = True if r['type_id'] == "35836" else False
                location = event['moon_id']

                # Save info.
                ref = Refinery(location=moon, name=refName, structure_id=event['structure_id'],
                               owner=EveCorporationInfo.objects.get(corporation_id=owner), size=size).save()
                ref = Refinery.objects.get(structure_id=event['structure_id'])

            # Times
            # Format: 2018-11-01T00:00:59Z
            arrival_time = event['chunk_arrival_time']
            start_time = event['extraction_start_time']
            decay_time = event['natural_decay_time']

            extract = ExtractEvent.objects.get_or_create(start_time=start_time, decay_time=decay_time,
                                                         arrival_time=arrival_time, structure=ref, moon=moon,
                                                         corp=ref.owner)
    except Exception as e:
        ctx['debug'] = e
    return render(request, 'moonstuff/moon_index.html', ctx)
