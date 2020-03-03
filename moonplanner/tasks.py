import logging
import yaml
import datetime

import pytz
from celery import shared_task

from django.db import transaction, IntegrityError
from django.contrib.auth.models import User

from allianceauth.eveonline.models import EveCharacter
from allianceauth.notifications import notify

from evesde.models import EveType, EveSolarSystem
from esi.clients import esi_client_factory
from esi.errors import TokenExpiredError, TokenInvalidError
from esi.models import Token

from .models import (
    Moon, 
    MoonProduct, 
    MiningCorporation, 
    MarketPrice, 
    Extraction, 
    ExtractionProduct,
    Refinery
)
from .app_settings import (
    MOONPLANNER_REPROCESSING_YIELD, MOONPLANNER_VOLUME_PER_MONTH
)
from .utils import LoggerAddTag, make_logger_prefix, get_swagger_spec_path


# add custom tag to logger with name of this app
logger = LoggerAddTag(logging.getLogger(__name__), __package__)

REFINERY_GROUP_ID = 1406
MOON_GROUP_ID = 8
MAX_DISTANCE_TO_MOON_METERS = 3000000


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
def process_survey_input(scans, user_pk=None):
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
        if line[0] == '':
            pass
        else:
            sublists.append(lines.index(line))

    # Separate out individual scans
    scans = []
    for i in range(len(sublists)):
        # The First List
        if i == 0:
            if i + 2 > len(sublists):
                scans.append(lines[sublists[i]:])
            else:
                scans.append(lines[sublists[i]:sublists[i + 1]])
        else:
            if i + 2 > len(sublists):
                scans.append(lines[sublists[i]:])
            else:
                scans.append(lines[sublists[i]:sublists[i + 1]])
    
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
                        'solar_system_id': solar_system_id,
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
                    MOONPLANNER_VOLUME_PER_MONTH, 
                    MOONPLANNER_REPROCESSING_YIELD
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
        
    # send result notification to user
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
def run_refineries_update(mining_corp_pk, user_pk=None):
    """update list of refineries with extractions for a mining corporation"""
    
    try:                
        addTag = make_logger_prefix('(none)')
        try:
            mining_corp = MiningCorporation.objects.get(pk=mining_corp_pk)
        except MiningCorporation.DoesNotExist as ex:        
            raise MiningCorporation.DoesNotExist(
                'task called for non existing corp with pk {}'.format(
                    mining_corp_pk
                )
            )
            raise ex
        else:
            addTag = make_logger_prefix(
                'update_refineries: {}'.format(mining_corp)
            )
        
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
            spec_file=get_swagger_spec_path()
        )
        
        # get all corporation structures
        logger.info(addTag('Fetching corp structures'))

        all_structures = client.Corporation\
            .get_corporations_corporation_id_structures(
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
                    structure_id=refinery['structure_id'],
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
        logger.info(addTag(
            'Process extraction events from {} notifications'.format(
                len(notifications)
            )
        ))
        with transaction.atomic():            
            last_extraction_started = dict()
            for notification in sorted(notifications, key=lambda k: k['timestamp']):

                if notification['type'] == 'MoonminingExtractionStarted':
                    parsed_text = yaml.safe_load(notification['text'])                                        
                    structure_id = parsed_text['structureID']
                    refinery = Refinery.objects.get(
                        structure_id=structure_id
                    )
                    extraction, created = Extraction.objects.get_or_create(
                        refinery=refinery,
                        ready_time=ldapTime2datetime(parsed_text['readyTime']),
                        defaults={
                            'auto_time': ldapTime2datetime(parsed_text['autoTime'])
                        }                    
                    )
                    last_extraction_started[structure_id] = extraction
                    
                    ore_volume_by_type = parsed_text['oreVolumeByType'].items()
                    for ore_type_id, ore_volume in ore_volume_by_type:
                        ExtractionProduct.objects.get_or_create(
                            extraction=extraction,
                            ore_type_id=ore_type_id,
                            defaults={
                                'volume': ore_volume
                            }
                        )

                # remove latest started extraction if it was canceled 
                # and not finished
                if notification['type'] == 'MoonminingExtractionCancelled':
                    parsed_text = yaml.safe_load(notification['text'])                    
                    structure_id = parsed_text['structureID']
                    if structure_id in last_extraction_started:
                        extraction = last_extraction_started[structure_id]                        
                        extraction.delete()                        

                if notification['type'] == 'MoonminingExtractionFinished':
                    parsed_text = yaml.safe_load(notification['text'])                    
                    structure_id = parsed_text['structureID']
                    if structure_id in last_extraction_started:
                        del last_extraction_started[structure_id]
                    
    except Exception as ex:
        logger.error(addTag('An unexpected error occurred: {}'. format(ex)))
        success = False        
        raise ex
    else:
        success = True
    
    if user_pk:    
        message = (
            'The following refineries from {} have been added '
            'or updated:\n\n'.format(
                mining_corp
            )
        )
        for report in user_report:
            message += '{} @ {}\n'.format(
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
        logger.info('Starting ESI client...')
        client = esi_client_factory()
        logger.info('Fetching market prices from ESI...')
        market_data = client.Market.get_markets_prices().result()
        logger.info('Storing market prices...')
        for row in market_data:
            average_price = row['average_price'] \
                if 'average_price' in row else None
            adjusted_price = row['adjusted_price'] \
                if 'adjusted_price' in row else None
            try:
                MarketPrice.objects.update_or_create(
                    type_id=row['type_id'],
                    defaults={
                        'average_price': average_price,
                        'adjusted_price': adjusted_price,
                    }
                )
            except IntegrityError as error:
                # ignore rows which no matching evetype in the DB
                logger.info(
                    'failed to add row for type ID {} due to '
                    'IntegrityError: {}'.format(row['type_id'], error)
                )

        logger.info(
            'Started re-calculating moon income for {:,} moons'.format(
                Moon.objects.count()
            )
        )
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
