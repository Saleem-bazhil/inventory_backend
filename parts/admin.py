from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import PartRequest


@admin.register(PartRequest)
class PartRequestAdmin(ModelAdmin):
    list_display = (
        'id', 'part_number', 'part_name', 'quantity',
        'urgency', 'status', 'requested_by', 'created_at',
    )
    search_fields = ('part_number', 'part_name', 'description')
    list_filter = ('status', 'urgency')
    list_filter_submit = True
    readonly_fields = ('created_at', 'updated_at')
