from django.conf.urls import url

from . import views

app_name = 'moonstuff'

urlpatterns = [
    url(r'^$', views.moon_index, name='moon_index')
]
