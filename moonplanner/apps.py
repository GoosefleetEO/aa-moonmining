from django.apps import AppConfig

from . import __version__


class MoonPlanerConfig(AppConfig):
    name = "moonplanner"
    label = "moonplanner"
    verbose_name = "Moon Planner v{}".format(__version__)
