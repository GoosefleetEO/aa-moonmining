from django.urls import path

from . import views

app_name = "moonmining"

urlpatterns = [
    path("", views.index, name="index"),
    path("add_owner", views.add_owner, name="add_owner"),
    path("upload_survey", views.upload_survey, name="upload_survey"),
    path("modal_loader_body", views.modal_loader_body, name="modal_loader_body"),
    path("tests", views.tests, name="tests"),
    # extractions
    path("extractions", views.extractions, name="extractions"),
    path(
        "extractions_data/<str:category>",
        views.extractions_data,
        name="extractions_data",
    ),
    path(
        "extraction/<int:extraction_pk>",
        views.extraction_details,
        name="extraction_details",
    ),
    path(
        "extraction_ledger/<int:extraction_pk>",
        views.extraction_ledger,
        name="extraction_ledger",
    ),
    # moons
    path("moons", views.moons, name="moons"),
    # path("moons_data/<str:category>", views.moons_data, name="moons_data"),
    path("moons_data/<str:category>", views.MoonListJson.as_view(), name="moons_data"),
    path("moons_fdd_data/<str:category>", views.moons_fdd_data, name="moons_fdd_data"),
    path("moon/<int:moon_pk>", views.moon_details, name="moon_details"),
    # reports
    path("reports", views.reports, name="reports"),
    path(
        "report_owned_value_data",
        views.report_owned_value_data,
        name="report_owned_value_data",
    ),
    path(
        "report_user_mining_data",
        views.report_user_mining_data,
        name="report_user_mining_data",
    ),
    path(
        "report_user_uploaded_data",
        views.report_user_uploaded_data,
        name="report_user_uploaded_data",
    ),
    path(
        "report_ore_prices_data",
        views.report_ore_prices_data,
        name="report_ore_prices_data",
    ),
]
