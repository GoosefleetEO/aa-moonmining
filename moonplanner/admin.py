from django.contrib import admin

from . import tasks
from .models import Extraction, MiningCorporation, Moon, MoonProduct, Refinery


@admin.register(Extraction)
class ExtractionAdmin(admin.ModelAdmin):
    list_display = ("refinery", "ready_time")
    ordering = ("ready_time",)
    list_filter = (
        "refinery",
        "ready_time",
    )

    search_fields = ("moon__name",)


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


@admin.register(Refinery)
class RefineryAdmin(admin.ModelAdmin):
    list_display = ("name", "moon", "corporation", "type")
    list_filter = (
        "corporation__corporation",
        ("type", admin.RelatedOnlyFieldListFilter),
    )


admin.site.register(Moon)


admin.site.register(MoonProduct)
