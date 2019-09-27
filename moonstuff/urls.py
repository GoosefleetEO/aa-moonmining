from django.conf.urls import url

from . import views

app_name = 'moonstuff'

urlpatterns = [
    url(r'^$', views.moon_index, name='moon_index'),
    url(r'^add/$', views.add_token, name='add_token'),
    url(r'^moon/(?P<moonid>[0-9]+)/$', views.moon_info, name='moon_info'),
    url(r'^moon/scan/$', views.moon_scan, name='moon_scan'),
    url(r'^list_data/(?P<category>\w+)/$', views.moon_list_data, name='moon-list-data'),
    url(r'^list/$', views.moon_list, name='moon_list'),
    url(r'^list_all/$', views.moon_list_all, name='moon-list-all'),
]
