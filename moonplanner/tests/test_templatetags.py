import datetime as dt

from django.test import TestCase

from ..templatetags import moonplanner


class TestFormatisk(TestCase):
    def test_should_return_formatted_string_from_number_1(self):
        # when
        result = moonplanner.formatisk(1260000000)
        # then
        self.assertEqual(result, "1.3 B")

    def test_should_return_formatted_string_from_number_2(self):
        # when
        result = moonplanner.formatisk(123456789)
        # then
        self.assertEqual(result, "0.1 B")

    def test_should_return_formatted_string_from_string(self):
        # when
        result = moonplanner.formatisk("1234567890")
        # then
        self.assertEqual(result, "1.2 B")

    def test_should_return_none_when_type_invalid(self):
        # when
        result = moonplanner.formatisk("invalid")
        # then
        self.assertIsNone(result)


class TestDatetime(TestCase):
    def test_should_return_formatted_datetime(self):
        # when
        result = moonplanner.datetime(dt.datetime(2021, 3, 24, 14, 50))
        # then
        self.assertEqual(result, "2021-Mar-24 14:50")

    def test_should_return_none_for_invalid_types_1(self):
        # when
        result = moonplanner.datetime("invalid")
        # then
        self.assertIsNone(result)

    def test_should_return_none_for_invalid_types_2(self):
        # when
        result = moonplanner.datetime(42)
        # then
        self.assertIsNone(result)
