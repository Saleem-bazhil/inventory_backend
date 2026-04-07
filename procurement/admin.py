from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import BufferStock, POItem, PurchaseOrder, StockItem, StockMovement


class POItemInline(TabularInline):
    model = POItem
    extra = 1
    fields = ('part_number', 'part_name', 'quantity', 'unit_price', 'total', 'received_qty')


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(ModelAdmin):
    list_display = (
        'po_number', 'supplier_name', 'status',
        'total_amount', 'ordered_by', 'order_date', 'created_at',
    )
    search_fields = ('po_number', 'supplier_name', 'supplier_email')
    list_filter = ('status', 'region')
    list_filter_submit = True
    readonly_fields = ('po_number', 'created_at', 'updated_at')
    inlines = [POItemInline]


@admin.register(POItem)
class POItemAdmin(ModelAdmin):
    list_display = ('id', 'purchase_order', 'part_number', 'part_name', 'quantity', 'received_qty')
    search_fields = ('part_number', 'part_name')
    readonly_fields = ('created_at',)


@admin.register(StockItem)
class StockItemAdmin(ModelAdmin):
    list_display = (
        'part_number', 'part_name', 'category', 'brand',
        'qty_on_hand', 'qty_reserved', 'qty_on_order',
        'reorder_level', 'region', 'storage_location',
    )
    search_fields = ('part_number', 'part_name', 'description', 'category', 'brand')
    list_filter = ('category', 'brand', 'region')
    list_filter_submit = True
    readonly_fields = ('created_at', 'updated_at')


@admin.register(StockMovement)
class StockMovementAdmin(ModelAdmin):
    list_display = (
        'id', 'stock_item', 'movement_type', 'quantity',
        'performed_by', 'created_at',
    )
    search_fields = ('stock_item__part_number', 'notes')
    list_filter = ('movement_type',)
    list_filter_submit = True
    readonly_fields = ('created_at',)


@admin.register(BufferStock)
class BufferStockAdmin(ModelAdmin):
    list_display = (
        'id', 'stock_item', 'quantity', 'reserved_by',
        'is_active', 'expires_at', 'created_at',
    )
    search_fields = ('stock_item__part_number', 'reason')
    list_filter = ('is_active',)
    list_filter_submit = True
    readonly_fields = ('created_at',)
