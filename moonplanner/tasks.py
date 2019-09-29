import os
import logging
import yaml
from celery import shared_task
from django.db import utils, transaction
from django.contrib.auth.models import User
from esi.models import Token
from esi.clients import esi_client_factory
from allianceauth.notifications import notify
from .models import *
from .config import get_config

logger = logging.getLogger(__name__)

# add custom tag to logger with name of this app
class LoggerAdapter(logging.LoggerAdapter):
    def __init__(self, logger, prefix):
        super(LoggerAdapter, self).__init__(logger, {})
        self.prefix = prefix

    def process(self, msg, kwargs):
        return '[%s] %s' % (self.prefix, msg), kwargs

logger = logging.getLogger(__name__)
logger = LoggerAdapter(logger, __package__)

"""
Swagger Operations:
get_characters_character_id
get_characters_character_id_notifications
get_universe_structures_structure_id
get_universe_moons_moon_id
get_corporation_corporation_id
get_corporation_corporation_id_mining_extractions
post_universe_names
"""

config = get_config()

def _get_tokens(scopes):
    try:
        tokens = []
        characters = MoonDataCharacter.objects.all()
        for character in characters:
            tokens.append(Token.objects.filter(character_id=character.character.character_id).require_scopes(scopes)[0])
        return tokens
    except Exception as e:
        print(e)
        return False


@shared_task
def process_survey_input(scans, user_id = None):
    """process raw moon survey input from user
    
    Args:
        scans: raw text input from user containing moon survey data
        user_id: (optional) id of user who submitted the data
    """

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
    
    process_results = list()    
    for scan in scans:
        try:
            with transaction.atomic():
                moon_name = scan[0][0]
                system_id = scan[1][4]
                moon_id = scan[1][6]
                moon, _ = Moon.objects.get_or_create(
                    moon_id=moon_id,
                    defaults={
                        'system_id':system_id,
                        'income': None
                    }
                )
                moon.moonproduct_set.all().delete()
                scan = scan[1:]
                for product_data in scan:
                    # Trim off the empty index at the front
                    product_data = product_data[1:]            
                    MoonProduct.objects.create(
                        moon=moon,
                        amount=product_data[1],
                        ore_type_id=product_data[2]
                    )
                moon.income = moon.calc_income_estimate(
                    config['total_volume_per_month'], 
                    config['reprocessing_yield']
                )
                moon.save()
                logger.info('Added moon scan for {}'.format(moon.moon.evename))
        except Exception as e:
            logger.info(
                'An issue occurred while processing the following '
                + 'moon scan. {}'.format(scan)
            )
            logger.info(e)
            error_id = type(e).__name__
            success = False
            raise e
        else:
            success = True
            error_id = None
        
        process_results.append({
            'moon_name': moon_name,
            'success': success,
            'error_id': error_id
        }) 
        
    #send result notification to user
    success = True
    message = 'We have completed processing your moon survey input:\n\n'
    n = 0
    for result in process_results:
        n = n + 1
        name = result['moon_name']
        if result['success']:            
            status = 'OK'
            error_id = ''
        else:            
            status = 'FAILED'
            success = False
            error_id = '- {}'.format(result['error_id'])
        message += '#{}: {}: {} {}\n'. format(n, name, status, error_id)        

    if user_id:    
        notify(
            user=User.objects.get(pk=user_id),
            title='Moon survey input processing results: {}'.format(
                'OK' if success else 'FAILED'
            ),
            message=message,
            level='success' if success else 'danger'
        )

    return success

@shared_task
def check_notifications(token):
    c = token.get_esi_client()

    # Get notifications
    notifications = c.Character.get_characters_character_id_notifications(character_id=token.character_id).result()
    char = MoonDataCharacter.objects.get(character__character_id=token.character_id)
    moon_pops = []

    moon_ids = Moon.objects.all().values_list('moon_id', flat=True)
    print(moon_ids)

    for noti in notifications:
        if ("MoonminingExtraction" in noti['type']) and ("Cancelled" not in noti['type']):
            # Parse the notification
            text = noti['text']
            parsed_text = yaml.load(text)

            total_ore = 0
            # Get total volume, so we can calculate percentages
            for k, v in parsed_text['oreVolumeByType'].items():
                total_ore += int(v)
            # Replace volume with percent in oreVolumeByType
            for k, v in parsed_text['oreVolumeByType'].items():
                percentage = int(v) / total_ore
                parsed_text['oreVolumeByType'][k] = percentage

            moon_pops.append(parsed_text)

    # Process notifications
    for pop in moon_pops:
        if pop['moonID'] in moon_ids:
            moon = Moon.objects.get(moon_id=pop['moonID'])
            moon.resources.clear()
            # Get ore names
            types = []
            for k in pop['oreVolumeByType']:
                types.append(int(k))
            names = c.Universe.post_universe_names(ids=types).result()
            types = {}
            for name in names:
                types[name['id']] = name['name']
            # Create the resources.
            for k, v in pop['oreVolumeByType'].items():
                # Truncate amount to ensure duplicates are caught correctly
                v = float('%.10f' % v)
                resource, _ = MoonProduct.objects.get_or_create(ore=types[k], amount=v, type_id=k)
                moon.resources.add(resource.pk)
                

@shared_task
def import_data():
    # Get tokens
    req_scopes = [
        'esi-industry.read_corporation_mining.v1',
        'esi-universe.read_structures.v1',
        'esi-characters.read_notifications.v1'
    ]

    tokens = _get_tokens(req_scopes)
    print(tokens)

    for token in tokens:
        c = token.get_esi_client()
        try:
            char = c.Character.get_characters_character_id(character_id=token.character_id).result()
            corp_id = char['corporation_id']
            try:
                corp = EveCorporationInfo.objects.get(corporation_id=corp_id)
            except:
                corp = EveCorporationInfo.objects.create_corporation(corp_id=corp_id)
            e = c.Industry.get_corporation_corporation_id_mining_extractions(corporation_id=corp_id).result()
            for event in e:
                # Gather structure information.
                try:
                    moon = Moon.objects.get(moon_id=event['moon_id'])
                except models.ObjectDoesNotExist:
                    # Moon Info
                    m = c.Universe.get_universe_moons_moon_id(moon_id=event['moon_id']).result()
                    moon, created = Moon.objects.get_or_create(moon_id=event['moon_id'], system_id=m['system_id'],
                                                               name=m['name'])

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
                try:
                    extract = ExtractEvent.objects.get_or_create(start_time=start_time, decay_time=decay_time,
                                                                 arrival_time=arrival_time, structure=ref, moon=moon,
                                                                 corp=ref.owner)
                except utils.IntegrityError:
                    continue
            logger.info("Imported extraction data from %s" % token.character_id)
        except Exception as e:
            logger.error("Error importing data extraction data from %s" % token.character_id)
            logger.error(e)

        check_notifications(token)


@shared_task
def update_moon_income():
    """update the income for all moons"""

    try:
        logger.info('Updating market prices from ESI')
        
        client = esi_client_factory()    
        
        with transaction.atomic():
            MarketPrice.objects.all().delete()
            for row in client.Market.get_markets_prices().result():
                MarketPrice.objects.create(
                    type_id=row['type_id'],
                    average_price=row['average_price'] if 'average_price' in row else None,
                    adjusted_price=row['adjusted_price'] if 'adjusted_price' in row else None,
                )

        logger.info(
            'Started re-calculating moon income for {:,} moons'.format(
                Moon.objects.count()
        ))
        with transaction.atomic():
            for moon in Moon.objects.all():
                moon.income = moon.calc_income_estimate(
                    config['total_volume_per_month'], 
                    config['reprocessing_yield']
                )
                moon.save()
        logger.info('Completed re-calculating moon income')

    except Exception as ex:
        logger.error('An unexpected error occurred: {}'.format(ex))