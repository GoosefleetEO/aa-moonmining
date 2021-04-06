import datetime as dt

from django.test import TestCase

from .. import helpers


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
