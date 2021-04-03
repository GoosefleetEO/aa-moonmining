from django.utils.translation import ugettext_lazy as _

from allianceauth import hooks
from allianceauth.services.hooks import MenuItemHook, UrlHook

from . import __title__, urls


class MoonMenu(MenuItemHook):
    def __init__(self):
        MenuItemHook.__init__(
            self,
            _(__title__),
            "fas fa-moon fa-fw",
            "moonmining:index",
            navactive=["moonmining:"],
        )

    def render(self, request):
        if request.user.has_perm("moonmining.basic_access"):
            return MenuItemHook.render(self, request)
        return ""


@hooks.register("menu_item_hook")
def register_menu():
    return MoonMenu()


@hooks.register("url_hook")
def register_url():
    return UrlHook(urls, "moonmining", r"^moonmining/")
