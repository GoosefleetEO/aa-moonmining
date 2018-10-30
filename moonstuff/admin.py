from django.contrib import admin
from .models import *


# Register your models here.
@admin.register(ExtractEvent)
class ExtractEventAdmin(admin.ModelAdmin):
    list_display = ('moon', 'arrival_time')
    ordering = ('arrival_time',)

    search_fields = ('moon__name',)


admin.site.register(Moon)
admin.site.register(Refinery)
