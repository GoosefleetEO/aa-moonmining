from django.conf.urls import url

from . import views

app_name = 'moonplanner'

urlpatterns = [
    url(r'^$', views.index, name='index'),
    url(r'^extractions$', views.extractions, name='extractions'),
    url(r'^add_corporation/$', views.add_mining_corporation, name='add_mining_corporation'),    
    url(r'^add_moon_scan/$', views.add_moon_scan, name='add_moon_scan'),
    url(
        r'^list_data/(?P<category>\w+)/$', 
        views.moon_list_data, 
        name='moon_list_data'
    ),
    url(r'^our_moons/$', views.moon_list_ours, name='moon_list_ours'),
    url(r'^all_moons/$', views.moon_list_all, name='moon_list_all'),
    url(r'^moon/(?P<moonid>[0-9]+)/$', views.moon_info, name='moon_info'),
]
