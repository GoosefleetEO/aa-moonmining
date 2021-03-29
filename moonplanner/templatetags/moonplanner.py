import datetime as dt
from typing import Optional

from django import template

from .. import constants

register = template.Library()


@register.filter
def formatisk(value) -> Optional[str]:
    """Return the formatted ISK value or None if input was invalid."""
    try:
        return "{:,.1f} B".format(float(value) / constants.VALUE_DIVIDER)
    except (ValueError, TypeError):
        return None


@register.filter
def datetime(value: dt.datetime) -> Optional[str]:
    try:
        return value.strftime(constants.DATETIME_FORMAT)
    except AttributeError:
        return None
