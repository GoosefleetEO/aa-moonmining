from django.urls import path

from . import views

app_name = "moonplanner"

urlpatterns = [
    path("", views.index, name="index"),
    path(
        "add_corporation", views.add_mining_corporation, name="add_mining_corporation"
    ),
    path("add_moon_scan", views.add_moon_scan, name="add_moon_scan"),
    path("extractions", views.extractions, name="extractions"),
    path(
        "extraction_list_data/<str:category>",
        views.extraction_list_data,
        name="extraction_list_data",
    ),
    path("moons", views.moon_list, name="moon_list"),
    path("moon_list_data/<str:category>", views.moon_list_data, name="moon_list_data"),
    path("moon/<int:moon_pk>", views.moon_info, name="moon_info"),
]
