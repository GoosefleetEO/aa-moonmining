import datetime as dt

from django.test import TestCase

from .. import helpers
from .testdata.factories import UserMainFactory


class TestRoundDatetime(TestCase):
    def test_should_round_up(self):
        # given
        my_dt = dt.datetime(2021, 4, 6, 20, 15, 0, 567000)
        # when/then
        self.assertEqual(
            dt.datetime(2021, 4, 6, 20, 15, 1), helpers.round_seconds(my_dt)
        )

    def test_should_round_down(self):
        # given
        my_dt = dt.datetime(2021, 4, 6, 20, 15, 0, 267000)
        # when/then
        self.assertEqual(
            dt.datetime(2021, 4, 6, 20, 15, 0), helpers.round_seconds(my_dt)
        )

    def test_should_do_nothing(self):
        # given
        my_dt = dt.datetime(2021, 4, 6, 20, 15, 0)
        # when/then
        self.assertEqual(
            dt.datetime(2021, 4, 6, 20, 15, 0), helpers.round_seconds(my_dt)
        )


class TestUserPermLookup(TestCase):
    def test_should_return_lookup(self):
        # given
        user = UserMainFactory(permissions=["moonmining.extractions_access"])
        # when
        result = helpers.user_perms_lookup(
            user, ["moonmining.extractions_access", "moonmining.view_all_moons"]
        )
        # then
        excepted = {
            "moonmining": {
                "extractions_access": True,
                "view_all_moons": False,
            }
        }
        self.assertDictEqual(result, excepted)
