from django.http import HttpResponse


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
