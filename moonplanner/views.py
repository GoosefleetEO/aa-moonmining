import os
import urllib
from datetime import date, datetime, timedelta, timezone
import logging
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.forms.models import model_to_dict
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.cache import cache_page
from django.db.models import prefetch_related_objects
from esi.decorators import token_required
from esi.clients import esi_client_factory
from evesde.models import EveTypeMaterial
from .models import *
from .forms import MoonScanForm
from .tasks import process_survey_input, import_data
from .config import get_config

logger = logging.getLogger(__name__)

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

config = get_config()

# Create your views here.
@login_required
@permission_required('moonplanner.access_moonplanner')
def moon_index(request):
    ctx = {}
    # Upcoming Extractions
    today = datetime.today().replace(tzinfo=timezone.utc)
    end = today + timedelta(days=7)
    ctx['exts'] = ExtractEvent.objects.filter(arrival_time__gte=today, arrival_time__lte=end)
    ctx['r_exts'] = ExtractEvent.objects.filter(arrival_time__lt=today).order_by('-arrival_time')[:10]

    return render(request, 'moonplanner/moon_index.html', ctx)


@login_required
@permission_required('moonplanner.access_moonplanner')
def moon_info(request, moonid):
    ctx = {}
    if len(moonid) == 0 or not moonid:
        messages.warning(request, "You must specify a moon ID.")
        return redirect('moonplanner:moon_index')

    try:
        ctx['moon'] = moon = Moon.objects.get(moon_id=moonid)
        income = moon.calc_income_estimate(
            config['total_volume_per_month'], 
            config['reprocessing_yield']
        )
        ctx['moon_income'] = None if income is None else income / 1000000000

        products = MoonProduct.objects.filter(moon=moon)
        product_rows = []
        if len(products) > 0:
            for product in products:
                image_url = "https://image.eveonline.com/Type/{}_64.png".format(
                    product.ore_type_id
                )                
                amount = int(round(product.amount * 100))
                income = moon.calc_income_estimate(
                    config['total_volume_per_month'], 
                    config['reprocessing_yield'],
                    product
                )
                ore_type_url = "https://www.kalkoken.org/apps/eveitems/?typeId={}".format(
                    product.ore_type_id
                )
                product_rows.append({
                    'ore_type_name': product.ore_type.type_name,
                    'ore_type_url': ore_type_url,
                    'ore_group_name': product.ore_type.group.group_name,
                    'image_url': image_url, 
                    'amount': amount, 
                    'income': None if income is None else income / 1000000000
                })
        ctx['product_rows'] = product_rows

        today = datetime.today().replace(tzinfo=timezone.utc)
        end = today + timedelta(days=30)
        ctx['pulls'] = ExtractEvent.objects.filter(
            moon=moon, 
            arrival_time__gte=today, 
            arrival_time__lte=end
        )
        ctx['ppulls'] = ExtractEvent.objects.filter(
            moon=moon, 
            arrival_time__lt=today
        )

    except models.ObjectDoesNotExist:
        messages.warning(request, "Moon {} does not exist in the database.".format(moonid))
        return redirect('moonplanner:moon_index')

    return render(request, 'moonplanner/moon_info.html', ctx)


@permission_required((
    'moonplanner.access_moonplanner', 
    'moonplanner.upload_moon_scan'
))
@login_required()
def moon_scan(request):
    if request.method == 'POST':
        form = MoonScanForm(request.POST)
        if form.is_valid():            
            scans = request.POST['scan']
            process_survey_input.delay(scans, request.user.pk)

            messages.success(
                request, 
                'Your scan has been submitted for processing. You will' 
                + 'receive a notification once processing is complete.')
            return render(request, 'moonplanner/add_scan.html')
        else:
            messages.error(
                request, 
                'Oh No! Something went wrong with your moon scan submission.'
            )
            return redirect('moonplanner:moon_info')
    else:
        return render(request, 'moonplanner/add_scan.html')


@login_required()
@permission_required('moonplanner.access_moonplanner')
def moon_list(request):    
    # render the page only, data is retrieved through ajax from moon_list_data
    context = {
        'title': 'Our Moons',
        'ajax_url': reverse('moonplanner:moon_list_data', args=['our_moons'])
    }    
    return render(request, 'moonplanner/moon_list.html', context)


@login_required()
@permission_required('moonplanner.access_moonplanner')
def moon_list_all(request):    
    # render the page only, data is retrieved through ajax from moon_list_data
    context = {
        'title': 'All Moons',
        'ajax_url': reverse('moonplanner:moon_list_data', args=['all_moons']),
        'reprocessing_yield': config['reprocessing_yield'] * 100,
        'total_volume_per_month': '{:,.1f}'.format(
            config['total_volume_per_month'] / 1000000
        )
    }                
    return render(request, 'moonplanner/moon_list.html', context)


#@cache_page(60 * 5)
@login_required()
@permission_required('moonplanner.access_moonplanner')
def moon_list_data(request, category):
    
    data = list()    
    if category == 'our_moons':
        moon_query = [
            r.location 
            for r in Refinery.objects.select_related('location')
        ] 
    else:
        moon_query = Moon.objects.select_related(
            'system__region', 'moon__evename'
        ).filter(system__region__region_id=10000030)
    for moon in moon_query:
        moon_details_url = reverse('moonplanner:moon_info', args=[moon.moon_id])
        solar_system_name = moon.system.solar_system_name
        solar_system_link = '<a href="https://evemaps.dotlan.net/system/{}" target="_blank">{}</a>'.format(
            urllib.parse.quote_plus(solar_system_name),
            solar_system_name
        ) 

        if moon.income is not None:
            income = '{:.1f}'.format(moon.income / 1000000000)
        else:
            income = '(no data)'

        moon_data = {
            'moon_name': str(moon.moon.evename),
            'solar_system_name': solar_system_name,
            'solar_system_link': solar_system_link,
            'region_name': moon.system.region.region_name,
            'income': income,
            'details': ('<a class="btn btn-primary btn-sm" href="{}" data-toggle="tooltip" data-placement="top" title="Show details in current window">'.format(moon_details_url)
                + '<span class="fa fa-eye fa-fw"></span></a>'
                + '&nbsp;&nbsp;<a class="btn btn-default btn-sm" href="{}" target="_blank" data-toggle="tooltip" data-placement="top" title="Open details in new window">'.format(moon_details_url)
                + '<span class="fa fa-window-restore fa-fw"></span></a>')
        }        
        data.append(moon_data)    
    return JsonResponse(data, safe=False)


@permission_required(('moonplanner.add_extractevent', 'moonplanner.access_moonplanner'))
@token_required(scopes=['esi-industry.read_corporation_mining.v1', 'esi-universe.read_structures.v1',
                        'esi-characters.read_notifications.v1'])
@login_required
def add_token(request, token):
    messages.success(request, "Token added!")
    char = EveCharacter.objects.get(character_id=token.character_id)
    char = MoonDataCharacter(character=char)
    char.save()
    return redirect('moonplanner:moon_index')
