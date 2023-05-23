import datetime as dt
from collections import defaultdict
from typing import List

from django.http import HttpResponse
from eveuniverse.models import EveEntity

from allianceauth.authentication.models import User


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


def eve_entity_get_or_create_esi_safe(id):
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


def user_perms_lookup(user: User, selected_permissions: List[str]) -> dict:
    """Create a lookup for user permissions.

    Allows to create a perms object in Javascript
    that looks like it's namesake in templates.
    """
    all_permissions = user.get_all_permissions()
    user_perms = defaultdict(dict)
    for permission in selected_permissions:
        app_name, perm_name = permission.split(".")
        user_perms[app_name][perm_name] = permission in all_permissions
    return user_perms
