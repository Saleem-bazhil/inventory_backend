from django.contrib import admin

from .models import (
    BufferAuditLog,
    BufferCase,
    BufferStockItem,
    CaseProof,
    InterRegionTransfer,
    OOWApproval,
    ReplenishmentOrder,
)


@admin.register(BufferStockItem)
class BufferStockItemAdmin(admin.ModelAdmin):
    list_display = ["part_number", "part_name", "region", "qty_on_hand", "qty_reserved", "qty_available"]
    list_filter = ["region", "category", "brand"]
    search_fields = ["part_number", "part_name"]


@admin.register(BufferCase)
class BufferCaseAdmin(admin.ModelAdmin):
    list_display = ["case_number", "case_type", "status", "region", "customer_name", "created_at"]
    list_filter = ["case_type", "status", "region"]
    search_fields = ["case_number", "case_id", "customer_name"]


@admin.register(OOWApproval)
class OOWApprovalAdmin(admin.ModelAdmin):
    list_display = ["buffer_case", "status", "requested_by", "approved_by", "responded_at"]
    list_filter = ["status"]


@admin.register(InterRegionTransfer)
class InterRegionTransferAdmin(admin.ModelAdmin):
    list_display = ["transfer_number", "part_number", "quantity", "source_region", "destination_region", "status"]
    list_filter = ["status", "source_region", "destination_region"]


@admin.register(ReplenishmentOrder)
class ReplenishmentOrderAdmin(admin.ModelAdmin):
    list_display = ["order_number", "part_number", "quantity", "region", "status"]
    list_filter = ["status", "region"]


@admin.register(CaseProof)
class CaseProofAdmin(admin.ModelAdmin):
    list_display = ["buffer_case", "proof_type", "uploaded_by", "uploaded_at"]


@admin.register(BufferAuditLog)
class BufferAuditLogAdmin(admin.ModelAdmin):
    list_display = ["action", "entity_type", "entity_id", "actor", "region", "created_at"]
    list_filter = ["action", "entity_type", "region"]
