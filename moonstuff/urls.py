from django.conf.urls import url

from . import views

app_name = 'moonstuff'

urlpatterns = [
    url(r'^$', views.moon_index, name='moon_index'),
    url(r'^import/$', views.import_data, name='import_data'),
    url(r'^moon/(?P<moonid>[0-9]+)/$', views.moon_info, name='moon_info')
]
