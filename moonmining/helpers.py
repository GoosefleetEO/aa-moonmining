import datetime as dt

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


def round_seconds(obj: dt.datetime) -> dt.datetime:
    """Return copy rounded to full seconds."""
    if obj.microsecond >= 500_000:
        obj += dt.timedelta(seconds=1)
    return obj.replace(microsecond=0)
