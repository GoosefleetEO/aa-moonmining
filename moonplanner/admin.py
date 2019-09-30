from django.contrib import admin
from .models import *


# Register your models here.
@admin.register(Extraction)
class ExtractionAdmin(admin.ModelAdmin):
    list_display = ('refinery', 'arrival_time')
    ordering = ('arrival_time',)

    search_fields = ('moon__name',)


admin.site.register(Moon)
admin.site.register(Refinery)
admin.site.register(MiningCorporation)
