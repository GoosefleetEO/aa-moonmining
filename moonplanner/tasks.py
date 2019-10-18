import os
import logging
import yaml
import datetime
import pytz
from celery import shared_task
from django.db import utils, transaction
from django.contrib.auth.models import User
from esi.clients import esi_client_factory
from esi.errors import TokenExpiredError, TokenInvalidError
from esi.models import Token
from allianceauth.notifications import notify
from .models import *
from .app_settings import *


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

SWAGGER_SPEC_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 
    'swagger.json'
)
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

REFINERY_GROUP_ID = 1406
MOON_GROUP_ID = 8
MAX_DISTANCE_TO_MOON_METERS = 3000000

def makeLoggerTag(tag: str):
    """creates a function to add logger tags"""
    return lambda text : '{}: {}'.format(tag, text)

def ldapTime2datetime(ldap_time: int) -> datetime:
    """converts ldap time to datatime"""    
    return pytz.utc.localize(datetime.datetime.utcfromtimestamp(
        (ldap_time / 10000000) - 11644473600
    ))    

"""
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
"""


@shared_task
def process_survey_input(scans, user_pk = None):
    """process raw moon survey input from user
    
    Args:
        scans: raw text input from user containing moon survey data
        user_pk: (optional) id of user who submitted the data
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
                solar_system_id = scan[1][4]
                moon_id = scan[1][6]
                moon, _ = Moon.objects.get_or_create(
                    moon_id=moon_id,
                    defaults={
                        'solar_system_id':solar_system_id,
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
                logger.info('Added moon scan for {}'.format(moon.name()))
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

    if user_pk:    
        notify(
            user=User.objects.get(pk=user_pk),
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
def update_refineries(mining_corp_pk, user_pk = None):
    """create or update refineries for a mining corporation"""
    
    try:                
        addTag = makeLoggerTag('(none)')
        try:
            mining_corp = MiningCorporation.objects.get(pk=mining_corp_pk)
        except MiningCorporation.DoesNotExist as ex:        
            raise MiningCorporation.DoesNotExist(
                'task called for non existing corp with pk {}'.format(mining_corp_pk)
            )
            raise ex
        else:
            addTag = makeLoggerTag('update_refineries: {}'.format(mining_corp))
        
        if mining_corp.character is None:
            logger.error(addTag('Missing character'))
            raise EveCharacter.DoesNotExist()

        try:
            token = Token.objects.filter(            
                character_id=mining_corp.character.character_id
            ).require_scopes(
                MiningCorporation.get_esi_scopes()
            ).require_valid().first()
        except TokenInvalidError as ex:        
            logger.error(addTag('Invalid token for fetching refineries'))
            raise ex
            
        except TokenExpiredError as ex:
            logger.error(addTag('Token expired'))
            raise ex
        
        else:
            logger.info(addTag(
                'Using token from {}'.format(mining_corp.character))
            )

        client = esi_client_factory(
            token=token, 
            spec_file=SWAGGER_SPEC_PATH
        )
        
        # get all corporation structures
        logger.info(addTag('Fetching corp structures'))

        all_structures = client.Corporation.get_corporations_corporation_id_structures(
            corporation_id=mining_corp.corporation.corporation_id
        ).result()

        # filter by refineres
        refinery_type_ids = [
            x.type_id for x in EveType.objects.filter(group_id=REFINERY_GROUP_ID)
        ]
        
        refinery_structures = [
            x for x in all_structures 
            if x['type_id'] in refinery_type_ids
        ]

        logger.info(addTag('Updating refineries'))
        # for each refinery
        user_report = list()
        for refinery in refinery_structures:
            # get structure details for refinery
            structure_info = client.Universe.get_universe_structures_structure_id(
                structure_id=refinery['structure_id']
            ).result()
            
            # determine moon next to refinery        
            solar_system = EveSolarSystem.objects.get(
                pk=structure_info['solar_system_id']
            )            
            moon_item = solar_system.get_nearest_celestials(
                structure_info['position']['x'],
                structure_info['position']['y'],
                structure_info['position']['z'],
                group_id=MOON_GROUP_ID, 
                max_distance=MAX_DISTANCE_TO_MOON_METERS
            )

            if moon_item is not None:                
                # create moon if it does not exist
                moon, _ = Moon.objects.get_or_create(
                    moon_id=moon_item.item_id,
                    defaults={
                        'solar_system': solar_system,
                        'income': None
                    }
                )

                # create refinery if it does not exist
                Refinery.objects.get_or_create(
                    structure_id = refinery['structure_id'],
                    defaults={
                        'name': structure_info['name'],
                        'type_id': structure_info['type_id'],
                        'moon': moon,
                        'corporation': mining_corp
                    }
                )
                user_report.append({
                    'moon_name': moon.name(),
                    'refinery_name': structure_info['name']
                })        

        # fetch notifications
        logger.info(addTag('Fetching notifications'))
        notifications = client.Character.get_characters_character_id_notifications(
            character_id=mining_corp.character.character_id
        ).result()
                
        # add extractions for refineries if any are found
        logger.info(addTag('Process extraction events'))        
        with transaction.atomic():            
            last_extraction_started = dict()
            for notification in sorted(notifications, key=lambda k: k['timestamp']):

                if notification['type'] == 'MoonminingExtractionStarted':
                    parsed_text = yaml.safe_load(notification['text'])
                                        
                    structure_id=parsed_text['structureID']
                    refinery = Refinery.objects.get(
                        structure_id=structure_id
                    )
                    extraction, created = Extraction.objects.get_or_create(
                        refinery=refinery,
                        arrival_time=ldapTime2datetime(parsed_text['readyTime']),
                        defaults={
                            'decay_time':ldapTime2datetime(parsed_text['autoTime'])
                        }                    
                    )
                    last_extraction_started[structure_id] = extraction
                    
                    for ore_type_id, ore_volume in parsed_text['oreVolumeByType'].items():
                        ExtractionProduct.objects.get_or_create(
                            extraction = extraction,
                            ore_type_id = ore_type_id,
                            defaults={
                                'volume': ore_volume
                            }
                        )

                # remove latest started extraction if it was canceled 
                # and not finished
                if notification['type'] == 'MoonminingExtractionCancelled':
                    parsed_text = yaml.safe_load(notification['text'])                    
                    structure_id=parsed_text['structureID']
                    if structure_id in last_extraction_started:
                        extraction = last_extraction_started[structure_id]                        
                        extraction.delete()                        

                if notification['type'] == 'MoonminingExtractionFinished':
                    parsed_text = yaml.safe_load(notification['text'])                    
                    structure_id=parsed_text['structureID']
                    if structure_id in last_extraction_started:
                        del last_extraction_started[structure_id]
                    
    except Exception as ex:
        logger.error(addTag('An unexpected error occurred: {}'. format(ex)))
        success = False        
        raise ex
    else:
        success = True
    
    if user_pk:    
        message = 'The following refineries from {} have been added:\n\n'.format(
            mining_corp
        )
        for report in user_report:
            message = '{} @ {}\n'.format(
                report['moon_name'],
                report['refinery_name'],
            )

        notify(
            user=User.objects.get(pk=user_pk),
            title='Adding refinery report: {}'.format(
                'OK' if success else 'FAILED'
            ),
            message=message,
            level='success' if success else 'danger'
        )


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
                    MOONPLANNER_VOLUME_PER_MONTH, 
                    MOONPLANNER_REPROCESSING_YIELD
                )
                moon.save()
        logger.info('Completed re-calculating moon income')

    except Exception as ex:
        logger.error('An unexpected error occurred: {}'.format(ex))