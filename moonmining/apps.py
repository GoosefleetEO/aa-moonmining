from django.apps import AppConfig

from . import __version__


class MoonPlanerConfig(AppConfig):
    name = "moonmining"
    label = "moonmining"
    verbose_name = "Moon Mining v{}".format(__version__)
