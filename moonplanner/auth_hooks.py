from . import urls
from django.utils.translation import ugettext_lazy as _
from allianceauth import hooks
from allianceauth.services.hooks import MenuItemHook, UrlHook


class MoonMenu(MenuItemHook):
    def __init__(self):
        MenuItemHook.__init__(self, 'Moon Planner',
                              'fa fa-moon-o fa-fw',
                              'moonplanner:add_moon_scan',
                              navactive=['moonplanner:'])

    def render(self, request):
        if request.user.has_perm('moonplanner.access_moonplanner'):
            return MenuItemHook.render(self, request)
        return ''


@hooks.register('menu_item_hook')
def register_menu():
    return MoonMenu()


@hooks.register('url_hook')
def register_url():
    return UrlHook(urls, 'moonplanner', r'^moonplanner/')
