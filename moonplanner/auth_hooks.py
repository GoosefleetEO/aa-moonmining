from django.utils.translation import ugettext_lazy as _

from allianceauth import hooks
from allianceauth.services.hooks import MenuItemHook, UrlHook

from . import urls


class MoonMenu(MenuItemHook):
    def __init__(self):
        MenuItemHook.__init__(
            self,
            _("Moon Planner"),
            "fas fa-moon fa-fw",
            "moonplanner:index",
            navactive=["moonplanner:"],
        )

    def render(self, request):
        if request.user.has_perm("moonplanner.basic_access"):
            return MenuItemHook.render(self, request)
        return ""


@hooks.register("menu_item_hook")
def register_menu():
    return MoonMenu()


@hooks.register("url_hook")
def register_url():
    return UrlHook(urls, "moonplanner", r"^moonplanner/")
