from django.contrib import admin

from . import tasks
from .models import Extraction, MiningCorporation, Moon, Refinery


@admin.register(Extraction)
class ExtractionAdmin(admin.ModelAdmin):
    list_display = ("refinery", "ready_time")
    ordering = ("ready_time",)
    list_filter = (
        "refinery",
        "ready_time",
    )

    search_fields = ("eve_moon__name",)

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False


@admin.register(MiningCorporation)
class MiningCorporationAdmin(admin.ModelAdmin):
    list_display = ("corporation", "character")
    actions = ["run_refineries_update"]

    def run_refineries_update(self, request, queryset):

        for obj in queryset:
            tasks.run_refineries_update.delay(
                mining_corp_pk=obj.pk, user_pk=request.user.pk
            )
            text = "Started updating refineries for: {} ".format(obj)
            text += ". You will receive a report once it is completed."

            self.message_user(request, text)

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False


@admin.register(Refinery)
class RefineryAdmin(admin.ModelAdmin):
    list_display = ("name", "moon", "corporation", "eve_type")
    list_filter = (
        ("eve_type", admin.RelatedOnlyFieldListFilter),
        "corporation__corporation",
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
