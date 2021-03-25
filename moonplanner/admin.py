from django.contrib import admin

from . import tasks
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

    def _corporation(self, obj):
        return obj.refinery.corporation

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False


@admin.register(MiningCorporation)
class MiningCorporationAdmin(admin.ModelAdmin):
    list_display = ("eve_corporation", "character_ownership")
    ordering = ["eve_corporation"]
    actions = ["update_mining_corporation"]

    def update_mining_corporation(self, request, queryset):
        for obj in queryset:
            tasks.update_mining_corporation.delay(mining_corp_pk=obj.pk)
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

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False
