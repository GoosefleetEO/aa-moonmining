from django.contrib import admin
from .models import Extraction, Moon, Refinery, MiningCorporation, MoonProduct


# Register your models here.
@admin.register(Extraction)
class ExtractionAdmin(admin.ModelAdmin):
    list_display = ('refinery', 'arrival_time')
    ordering = ('arrival_time',)
    list_filter = ('refinery', 'arrival_time', )

    search_fields = ('moon__name',)


@admin.register(MiningCorporation)
class MiningCorporationAdmin(admin.ModelAdmin):
    list_display = ('corporation', 'character')


@admin.register(Refinery)
class RefineryAdmin(admin.ModelAdmin):
    list_display = ('name', 'moon', 'corporation', 'type')
    list_filter = (
        'corporation__corporation', 
        ('type', admin.RelatedOnlyFieldListFilter)
    )

admin.site.register(Moon)
admin.site.register(MoonProduct)
