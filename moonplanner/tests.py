import os
import inspect
import logging
import sys
from django.test import TestCase
from evesde.models import *
from . import tasks
from .models import *

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(
    inspect.currentframe()
)))

# reconfigure logger so we get logging from tasks to console during test
c_handler = logging.StreamHandler(sys.stdout)
logger = logging.getLogger('moonplanner.tasks')
logger.level = logging.DEBUG
logger.addHandler(c_handler)

class TestTasks(TestCase):

    @classmethod
    def setUpClass(cls):
        super(TestTasks, cls).setUpClass()

        region, _ = EveRegion.objects.get_or_create(
            region_id=10000030,
            region_name='Heimatar'
        )
        EveSolarSystem.objects.get_or_create(
            region=region,
            solar_system_id=30002542,
            solar_system_name='Auga'
        )
        EveType.objects.get_or_create(
            type_id=45506,
            type_name='Cinnabar'
        )
        EveType.objects.get_or_create(
            type_id=46676,
            type_name='Cubic Bistot'
        )
        EveType.objects.get_or_create(
            type_id=46678,
            type_name='Flawless Arkonor'
        )
        EveType.objects.get_or_create(
            type_id=45492,
            type_name='Bitumens'
        )
        EveType.objects.get_or_create(
            type_id=46689,
            type_name='Stable Veldspar'
        )
        EveType.objects.get_or_create(        
            type_id=45494,
            type_name='Cobaltite'
        )
        EveItem.objects.get_or_create(
            item_id=40161708
        )
        EveItem.objects.get_or_create(
            item_id=40161709
        )


    def test_process_resources(self):
        with open(
            os.path.join(currentdir, 'test_data/moon_survey_input_2.txt'), 
            'r', 
            encoding='utf-8'
        ) as f:
            scans = f.read()

        # process 2 times: first against empty DB, 
        # second against existing objects
        for x in range(2):
            self.assertTrue(tasks.process_survey_input(scans))

            m1 = Moon.objects.get(pk=40161708)
            self.assertEqual(
                m1.moonproduct_set.count(),
                4
            )
            self.assertEqual(
                m1.moonproduct_set.get(ore_type_id=45506).amount, 
                0.19
            )
            self.assertEqual(
                m1.moonproduct_set.get(ore_type_id=46676).amount, 
                0.23
            )
            self.assertEqual(
                m1.moonproduct_set.get(ore_type_id=46678).amount, 
                0.25
            )
            self.assertEqual(
                m1.moonproduct_set.get(ore_type_id=46689).amount, 
                0.33
            )

            m2 = Moon.objects.get(pk=40161709)                
            self.assertEqual(
                m2.moonproduct_set.count(),
                4
            )
            self.assertEqual(
                m2.moonproduct_set.get(ore_type_id=45492).amount, 
                0.27
            )
            self.assertEqual(
                m2.moonproduct_set.get(ore_type_id=45494).amount, 
                0.23
            )
            self.assertEqual(
                m2.moonproduct_set.get(ore_type_id=46676).amount, 
                0.21
            )
            self.assertEqual(
                m2.moonproduct_set.get(ore_type_id=46678).amount, 
                0.29
            )

                
