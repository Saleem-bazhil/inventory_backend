from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import HPStockItem

@admin.register(HPStockItem)
class HPStockItemAdmin(ModelAdmin):
    list_display = ('case_id', 'work_order_id', 'region', 'status', 'created_at')
    search_fields = ('case_id', 'work_order_id', 'delivery_no', 'hp_sales_order_no')
    list_filter = ('status', 'region')
