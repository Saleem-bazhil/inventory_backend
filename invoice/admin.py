from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import Invoice, InvoiceItem


class InvoiceItemInline(TabularInline):
    model = InvoiceItem
    extra = 1
    fields = ('description', 'quantity', 'unit_price', 'total')


@admin.register(Invoice)
class InvoiceAdmin(ModelAdmin):
    list_display = (
        'invoice_number', 'customer_name', 'total',
        'status', 'paid_amount', 'due_date',
        'created_by', 'created_at',
    )
    search_fields = ('invoice_number', 'customer_name', 'customer_email')
    list_filter = ('status', 'region')
    list_filter_submit = True
    readonly_fields = ('invoice_number', 'created_at', 'updated_at')
    inlines = [InvoiceItemInline]


@admin.register(InvoiceItem)
class InvoiceItemAdmin(ModelAdmin):
    list_display = ('id', 'invoice', 'description', 'quantity', 'unit_price', 'total')
    search_fields = ('description',)
