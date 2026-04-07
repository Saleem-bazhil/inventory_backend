from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import Quotation, QuotationItem


class QuotationItemInline(TabularInline):
    model = QuotationItem
    extra = 1
    fields = ('description', 'quantity', 'unit_price', 'total')


@admin.register(Quotation)
class QuotationAdmin(ModelAdmin):
    list_display = (
        'quotation_number', 'ticket', 'total_amount',
        'status', 'prepared_by', 'created_at',
    )
    search_fields = ('quotation_number', 'notes')
    list_filter = ('status',)
    list_filter_submit = True
    readonly_fields = ('quotation_number', 'created_at', 'updated_at')
    inlines = [QuotationItemInline]


@admin.register(QuotationItem)
class QuotationItemAdmin(ModelAdmin):
    list_display = ('id', 'quotation', 'description', 'quantity', 'unit_price', 'total')
    search_fields = ('description',)
    readonly_fields = ('created_at',)
