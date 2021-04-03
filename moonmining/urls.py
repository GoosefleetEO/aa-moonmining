from django.urls import path

from . import views

app_name = "moonmining"

urlpatterns = [
    path("", views.index, name="index"),
    path("add_owner", views.add_owner, name="add_owner"),
    path("upload_survey", views.upload_survey, name="upload_survey"),
    path("extractions", views.extractions, name="extractions"),
    path(
        "extractions_data/<str:category>",
        views.extractions_data,
        name="extractions_data",
    ),
    path(
        "extraction_details/<int:extraction_pk>",
        views.extraction_details,
        name="extraction_details",
    ),
    path("moons", views.moons, name="moons"),
    path("moons_data/<str:category>", views.moons_data, name="moons_data"),
    path("moon/<int:moon_pk>", views.moon_details, name="moon_details"),
    path("reports", views.reports, name="reports"),
    path(
        "report_owned_value_data",
        views.report_owned_value_data,
        name="report_owned_value_data",
    ),
    path("modal_loader_body", views.modal_loader_body, name="modal_loader_body"),
]
