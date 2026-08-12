from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import HPStockItem, HPStockSettings

@admin.register(HPStockItem)
class HPStockItemAdmin(ModelAdmin):
    list_display = ('case_id', 'work_order_id', 'region', 'status', 'part_received_status', 'created_at')
    search_fields = ('case_id', 'work_order_id', 'delivery_no', 'hp_sales_order_no')
    list_filter = ('status', 'region', 'part_received_status', 'part_received_source')


@admin.register(HPStockSettings)
class HPStockSettingsAdmin(ModelAdmin):
    """Break-glass access to the singleton, for when the Settings page is not an
    option. Adding rows is blocked so the singleton stays a singleton."""
    list_display = ('received_spare_only', 'updated_by', 'updated_at')

    def has_add_permission(self, request):
        return not HPStockSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
