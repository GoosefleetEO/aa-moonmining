from django.contrib import admin

from .models import Extraction, Moon, Refinery, MiningCorporation, MoonProduct
from . import tasks

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
    actions = ['run_refineries_update']

    def run_refineries_update(self, request, queryset):
                        
        for obj in queryset:            
            tasks.run_refineries_update.delay(                
                mining_corp_pk=obj.pk,
                user_pk=request.user.pk
            )            
            text = 'Started updating refineries for: {} '.format(obj)
            text += '. You will receive a report once it is completed.'

            self.message_user(
                request, 
                text
            )


@admin.register(Refinery)
class RefineryAdmin(admin.ModelAdmin):
    list_display = ('name', 'moon', 'corporation', 'type')
    list_filter = (
        'corporation__corporation', 
        ('type', admin.RelatedOnlyFieldListFilter)
    )

admin.site.register(Moon)
admin.site.register(MoonProduct)
