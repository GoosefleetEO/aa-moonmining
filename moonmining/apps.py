from django.apps import AppConfig

from . import __version__


class MoonPlanerConfig(AppConfig):
    name = "moonmining"
    label = "moonmining"
    verbose_name = "Moon Planner v{}".format(__version__)
