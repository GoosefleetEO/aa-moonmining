from django.contrib import admin
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import gettext_lazy as _

from . import tasks
from .models import (
    EveOreType,
    EveOreTypeExtras,
    Extraction,
    ExtractionProduct,
    Label,
    MiningLedgerRecord,
    Moon,
    MoonProduct,
    Notification,
    Owner,
    Refinery,
)


class EveOreTypeExtrasInline(admin.StackedInline):
    model = EveOreTypeExtras


@admin.register(EveOreType)
class EveOreTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "_current_price", "_group", "_pricing_method")
    ordering = ("name",)
    list_filter = (
        "extras__pricing_method",
        ("eve_group", admin.RelatedOnlyFieldListFilter),
    )
    search_fields = ("name",)
    inlines = [EveOreTypeExtrasInline]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("extras", "eve_group")

    @admin.display(ordering="extras__current_price")
    def _current_price(self, obj):
        try:
            return f"{obj.extras.current_price:,.2f}"
        except (ObjectDoesNotExist, TypeError):
            return None

    @admin.display(ordering="eve_group__name")
    def _group(self, obj):
        return str(obj.eve_group)

    @admin.display(ordering="extras__pricing_method")
    def _pricing_method(self, obj):
        try:
            return obj.extras.get_pricing_method_display()
        except ObjectDoesNotExist:
            return None

    def has_add_permission(self, *args, **kwargs) -> bool:
        return False

    def has_change_permission(self, *args, **kwargs) -> bool:
        return False


class ExtractionProductAdmin(admin.TabularInline):
    model = ExtractionProduct


@admin.register(Extraction)
class ExtractionAdmin(admin.ModelAdmin):
    list_display = ("chunk_arrival_at", "status", "_owner", "refinery", "_ledger")
    ordering = ("-chunk_arrival_at",)
    list_filter = ("chunk_arrival_at", "status", "refinery__owner", "refinery")
    search_fields = ("refinery__moon__eve_moon__name",)
    inlines = [ExtractionProductAdmin]
    actions = ["update_calculated_properties"]

    @admin.display(
        description=_("Update calculated properties for selected extractions.")
    )
    def update_calculated_properties(self, request, queryset):
        num = 0
        for obj in queryset:
            tasks.update_extraction_calculated_properties.delay(extraction_pk=obj.pk)
            num += 1
        self.message_user(
            request,
            _("Started updating calculated properties for %d extractions." % num),
        )

    def _owner(self, obj):
        return obj.refinery.owner

    @admin.display(boolean=True)
    def _ledger(self, obj):
        if obj.status != Extraction.Status.COMPLETED:
            return None
        return obj.ledger.exists()

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False


@admin.register(Label)
class LabelAdmin(admin.ModelAdmin):
    list_display = ("name", "style")
    fields = ("name", "description", "style")


@admin.register(MiningLedgerRecord)
class MiningLedgerRecordAdmin(admin.ModelAdmin):
    list_display = ("refinery", "day", "user", "character", "ore_type", "quantity")
    ordering = ["refinery", "day", "user", "character", "ore_type"]
    list_filter = (
        "refinery",
        "day",
        "user",
        ("character", admin.RelatedOnlyFieldListFilter),
        "ore_type",
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("refinery", "character", "ore_type", "user")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class MoonHasRefineryFilter(admin.SimpleListFilter):
    title = "has refinery"
    parameter_name = "has_refinery"

    def lookups(self, request, model_admin):
        return (
            ("yes", _("Yes")),
            ("no", _("No")),
        )

    def queryset(self, request, queryset):
        """Return the filtered queryset"""
        if self.value() == "yes":
            return queryset.filter(refinery__isnull=False)
        elif self.value() == "no":
            return queryset.filter(refinery__isnull=True)
        return queryset


class MoonProductAdminInline(admin.TabularInline):
    model = MoonProduct

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Moon)
class MoonAdmin(admin.ModelAdmin):
    list_display = (
        "eve_moon",
        "_constellation",
        "_region",
        "label",
        "products_updated_at",
        "_refinery",
        "_owner",
    )
    list_filter = (
        "rarity_class",
        MoonHasRefineryFilter,
        "label",
        "products_updated_at",
        ("refinery__owner", admin.RelatedOnlyFieldListFilter),
        (
            "eve_moon__eve_planet__eve_solar_system__eve_constellation__eve_region",
            admin.RelatedOnlyFieldListFilter,
        ),
        (
            "eve_moon__eve_planet__eve_solar_system__eve_constellation",
            admin.RelatedOnlyFieldListFilter,
        ),
        ("eve_moon__eve_planet__eve_solar_system", admin.RelatedOnlyFieldListFilter),
    )
    actions = ["update_calculated_properties", "update_products_from_latest_extraction"]
    inlines = (MoonProductAdminInline,)
    fields = (
        "eve_moon",
        "rarity_class",
        "value",
        "label",
        "products_updated_at",
        "products_updated_by",
    )
    readonly_fields = (
        "eve_moon",
        "products_updated_at",
        "products_updated_by",
        "rarity_class",
        "value",
    )
    search_fields = [
        "eve_moon__name",
        "refinery__name",
        "refinery__owner__corporation__corporation_name",
        "refinery__owner__corporation__alliance__alliance_name",
    ]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related(
            "refinery",
            "refinery__owner",
            "refinery__owner__corporation",
            "refinery__owner__corporation__alliance",
            "eve_moon",
            "eve_moon__eve_planet__eve_solar_system",
            "eve_moon__eve_planet__eve_solar_system__eve_constellation",
            "eve_moon__eve_planet__eve_solar_system__eve_constellation__eve_region",
        )

    def has_add_permission(self, request):
        return False

    @admin.display(ordering="eve_moon__eve_planet__eve_solar_system")
    def _solar_system(self, obj) -> str:
        return obj.eve_moon.eve_planet.eve_solar_system

    @admin.display(ordering="eve_moon__eve_planet__eve_solar_system__eve_constellation")
    def _constellation(self, obj) -> str:
        return obj.eve_moon.eve_planet.eve_solar_system.eve_constellation

    @admin.display(
        ordering="eve_moon__eve_planet__eve_solar_system__eve_constellation__eve_region"
    )
    def _region(self, obj) -> str:
        return obj.eve_moon.eve_planet.eve_solar_system.eve_constellation.eve_region

    @admin.display(ordering="refinery__name")
    def _refinery(self, obj) -> str:
        return obj.refinery.name

    @admin.display(ordering="refinery__owner__name")
    def _owner(self, obj) -> str:
        return obj.refinery.owner.name

    @admin.display(description=_("Update calculated properties for selected moons."))
    def update_calculated_properties(self, request, queryset):
        num = 0
        for obj in queryset:
            tasks.update_moon_calculated_properties.delay(moon_pk=obj.pk)
            num += 1
        self.message_user(
            request, _("Started updating calculated properties for %d moons." % num)
        )

    @admin.display(
        description=_("Update products from latest extraction for selected moons.")
    )
    def update_products_from_latest_extraction(self, request, queryset):
        num = 0
        for obj in queryset:
            tasks.update_moon_products_from_latest_extraction.delay(moon_pk=obj.pk)
            num += 1
        self.message_user(
            request,
            _("Started updating products from latest extractions for %d moons." % num),
        )


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "notification_id",
        "owner",
        "notif_type",
        "timestamp",
        "created",
        "last_updated",
    )
    ordering = ["-timestamp"]
    list_filter = ("owner", "notif_type")

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False


@admin.register(Owner)
class OwnerAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "_alliance",
        "character_ownership",
        "is_enabled",
        "last_update_at",
        "last_update_ok",
    )
    ordering = ["corporation"]
    search_fields = ("refinery__moon__eve_moon__name",)
    list_filter = (
        "is_enabled",
        "last_update_ok",
        "corporation__alliance",
    )
    actions = ["update_owner"]

    @admin.display(ordering="corporation__alliance__alliance_name")
    def _alliance(self, obj):
        return obj.corporation.alliance

    @admin.display(description=_("Update selected owners from ESI"))
    def update_owner(self, request, queryset):
        for obj in queryset:
            tasks.update_owner.delay(obj.pk)
            text = _("Started updating owner %s." % obj)
            self.message_user(request, text)

    def has_add_permission(self, request):
        return False

    def get_readonly_fields(self, request, obj=None):
        if obj:  # editing an existing object
            return tuple(self.readonly_fields) + (
                "corporation",
                "character_ownership",
                "last_update_at",
                "last_update_ok",
            )
        return self.readonly_fields


@admin.register(Refinery)
class RefineryAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "moon",
        "owner",
        "eve_type",
        "ledger_last_update_ok",
        "ledger_last_update_at",
    )
    ordering = ["name"]
    list_filter = (
        ("owner__corporation", admin.RelatedOnlyFieldListFilter),
        "ledger_last_update_ok",
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related(
            "moon", "moon__eve_moon", "eve_type", "owner", "owner__corporation"
        )

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    actions = ["update_mining_ledger"]

    @admin.display(
        description=_("Update mining ledger for selected refineries from ESI")
    )
    def update_mining_ledger(self, request, queryset):
        for obj in queryset:
            tasks.update_mining_ledger_for_refinery.delay(obj.id)
            text = _("Started updating mining ledger %s." % obj)
            self.message_user(request, text)
