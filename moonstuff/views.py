from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from esi.decorators import token_required
import os
from datetime import date, datetime, timedelta, timezone
from .models import *
from .forms import MoonScanForm
from .tasks import process_resources, import_data

SWAGGER_SPEC_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'swagger.json')
"""
Swagger Operations:
get_characters_character_id
get_characters_character_id_notifications
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
    ctx['r_exts'] = ExtractEvent.objects.filter(arrival_time__lt=today).order_by('-arrival_time')[:10]

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
        ctx['ppulls'] = ExtractEvent.objects.filter(moon=ctx['moon'], arrival_time__lt=today)

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
            if len(lines[0]) == 0 or lines[0][0] == 'Moon':
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
                    if i+2 > len(sublists):
                        scans.append(lines[sublists[i]:])
                    else:
                        scans.append(lines[sublists[i]:sublists[i+1]])
                else:
                    if i+2 > len(sublists):
                        scans.append(lines[sublists[i]:])
                    else:
                        scans.append(lines[sublists[i]:sublists[i+1]])

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
def add_token(request, token):
    messages.success(request, "Token added!")
    return redirect('moonstuff:moon_index')
