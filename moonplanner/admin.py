import datetime as dt

from django.contrib import admin
from django.utils.timezone import now

from . import tasks
from .app_settings import MOONPLANNER_UPDATES_MINUTES_UNTIL_DELAYED
from .models import Extraction, MiningCorporation, Moon, Refinery


@admin.register(Extraction)
class ExtractionAdmin(admin.ModelAdmin):
    list_display = ("ready_time", "_corporation", "refinery")
    ordering = ("-ready_time",)
    list_filter = (
        "ready_time",
        "refinery__corporation",
        "refinery",
    )
    search_fields = ("refinery__moon__eve_moon__name",)

    actions = ["update_value"]

    def update_value(self, request, queryset):
        num = 0
        for obj in queryset:
            tasks.update_extraction_value.delay(extraction_pk=obj.pk)
            num += 1

        self.message_user(request, f"Started updating values for {num} extractions.")

    update_value.short_description = "Update value for selected extrations."

    def _corporation(self, obj):
        return obj.refinery.corporation

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False


@admin.register(MiningCorporation)
class MiningCorporationAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "_alliance",
        "character_ownership",
        "is_enabled",
        "last_update_at",
        "_updates_ok",
    )
    ordering = ["eve_corporation"]
    search_fields = ("refinery__moon__eve_moon__name",)
    list_filter = (
        "is_enabled",
        "eve_corporation__alliance",
    )
    actions = ["update_mining_corporation"]

    def _alliance(self, obj):
        return obj.eve_corporation.alliance

    _alliance.admin_order_field = "eve_corporation__alliance__alliance_name"

    def _updates_ok(self, obj):
        return (
            (
                now() - obj.last_update_at
                < dt.timedelta(minutes=MOONPLANNER_UPDATES_MINUTES_UNTIL_DELAYED)
            )
            if obj.last_update_at
            else None
        )

    _updates_ok.boolean = True

    def update_mining_corporation(self, request, queryset):
        for obj in queryset:
            tasks.update_mining_corporation.delay(corporation_pk=obj.pk)
            text = f"Started updating mining corporation: {obj}. "
            self.message_user(request, text)

    update_mining_corporation.short_description = (
        "Update refineres from ESI for selected mining corporations"
    )

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False


@admin.register(Refinery)
class RefineryAdmin(admin.ModelAdmin):
    list_display = ("name", "moon", "corporation", "eve_type")
    ordering = ["name"]
    list_filter = (
        ("eve_type", admin.RelatedOnlyFieldListFilter),
        "corporation__eve_corporation",
    )

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False


@admin.register(Moon)
class MoonAdmin(admin.ModelAdmin):
    list_display = ("eve_moon",)

    actions = ["update_value"]

    def update_value(self, request, queryset):
        num = 0
        for obj in queryset:
            tasks.update_moon_value.delay(moon_pk=obj.pk)
            num += 1

        self.message_user(request, f"Started updating values for {num} moons.")

    update_value.short_description = "Update value for selected moons."

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False
