from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required, permission_required
from esi.decorators import token_required
from esi.clients import esi_client_factory
import os
from datetime import date, datetime, timedelta, timezone
from allianceauth.eveonline.models import EveCorporationInfo
from .models import *
from .forms import MoonScanForm
from .tasks import process_resources

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
@permission_required('moonstuff.view_moonstuff')
def moon_index(request):
    ctx = {}
    # Upcoming Extractions
    today = datetime.today().replace(tzinfo=timezone.utc)
    end = today + timedelta(days=7)
    ctx['exts'] = ExtractEvent.objects.filter(arrival_time__gte=today, arrival_time__lte=end)

    return render(request, 'moonstuff/moon_index.html', ctx)


@login_required
@permission_required('moonstuff.view_moonstuff')
def moon_info(request, moonid):
    ctx = {}
    if len(moonid) == 0 or not moonid:
        messages.warning(request, "You must specify a moon ID.")
        return redirect('moonstuff:moon_index')

    try:
        ctx['moon'] = Moon.objects.get(moon_id=moonid)

        resources = Resource.objects.filter(moon=ctx['moon'])
        res = []
        if len(resources) > 0:
            for resource in resources:
                url = "https://image.eveonline.com/Type/{}_64.png".format(resource.ore_id)
                name = resource.ore
                amount = int(round(resource.amount * 100))
                res.append([name, url, amount])
        ctx['res'] = res

        today = datetime.today().replace(tzinfo=timezone.utc)
        end = today + timedelta(days=30)
        ctx['pulls'] = ExtractEvent.objects.filter(moon=ctx['moon'], arrival_time__gte=today, arrival_time__lte=end)

    except models.ObjectDoesNotExist:
        messages.warning(request, "Moon {} does not exist in the database.".format(moonid))
        return redirect('moonstuff:moon_index')

    return render(request, 'moonstuff/moon_info.html', ctx)


@permission_required(('moonstuff.view_moonstuff', 'moonstuff.add_resource'))
@login_required()
def moon_scan(request):
    ctx = {}
    if request.method == 'POST':
        form = MoonScanForm(request.POST)
        if form.is_valid():
            # Process the scan(s)... we might use celery to do this due to the possible size.
            scans = request.POST['scan']
            lines = scans.split('\n')
            lines_ = []
            for line in lines:
                line = line.strip('\r').split('\t')
                lines_.append(line)
            lines = lines_

            # Find all groups of scans.
            if len(lines[0]) is 0:
                lines = lines[1:]
            sublists = []
            for line in lines:
                # Find the lines that start a scan
                if line[0] is '':
                    pass
                else:
                    sublists.append(lines.index(line))

            # Separate out individual scans
            scans = []
            for i in range(len(sublists)):
                # The First List
                if i == 0:
                    if i+2>len(sublists):
                        scans.append(lines[sublists[i]:])
                    else:
                        scans.append(lines[sublists[i]:sublists[i+1]])
                else:
                    if i+2>len(sublists):
                        scans.append(lines[sublists[i]:])
                    else:
                        scans.append(lines[sublists[i]:sublists[i]])

            for scan in scans:
                process_resources.delay(scan)

            messages.success(request, "Your scan has been submitted for processing, depending on size this "
                                      "might take some time.\nYou can safely navigate away from this page.")
            return render(request, 'moonstuff/add_scan.html', ctx)
        else:
            messages.error(request, "Oh No! Something went wrong with your moon scan submission.")
            return redirect('moonstuff:moon_info')
    else:
        return render(request, 'moonstuff/add_scan.html')


@login_required()
@permission_required('moonstuff.view_moonstuff')
def moon_list(request):
    moon = Moon.objects.order_by('system_id', 'name')
    ctx = {'moons': moon}
    return render(request, 'moonstuff/moon_list.html', ctx)


@permission_required(('moonstuff.add_extractevent', 'moonstuff.view_moonstuff'))
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
        messages.success(request, "Extraction events successfully added!")
    except Exception as e:
        messages.error(request, "There was an error processing Extraction Events.\nError: %s" % e)
    return redirect('moonstuff:moon_index')
