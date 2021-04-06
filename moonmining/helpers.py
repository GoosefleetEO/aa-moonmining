import datetime as dt
from copy import copy

from django.http import HttpResponse
from eveuniverse.models import EveEntity


class EnumToDict:
    """Adds ability to an Enum class to be converted to a ordinary dict.

    This e.g. allows using Enums in Django templates.
    """

    @classmethod
    def to_dict(cls) -> dict:
        """Convert this enum to dict."""
        return {k: elem.value for k, elem in cls.__members__.items()}


class HttpResponseUnauthorized(HttpResponse):
    status_code = 401


def eveentity_get_or_create_esi_safe(id):
    """Get or Create EveEntity with given ID safely and return it. Else return None."""
    if id:
        try:
            entity, _ = EveEntity.objects.get_or_create_esi(id=id)
            return entity
        except OSError:
            pass
    return None


def round_seconds(dt_obj: dt.datetime) -> dt.datetime:
    """Return new copy rounded to full seconds."""
    new_dt_obj = copy(dt_obj)
    if new_dt_obj.microsecond >= 500_000:
        new_dt_obj += dt.timedelta(seconds=1)
    return new_dt_obj.replace(microsecond=0)
