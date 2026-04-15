from rest_framework import serializers

from .models import (
    BufferAuditLog,
    BufferCase,
    BufferStockItem,
    CaseProof,
    InterRegionTransfer,
    OOWApproval,
    ReplenishmentOrder,
)


# ─── Helpers ────────────────────────────────────────────────────────────────

def _user_name(user):
    if not user:
        return None
    name = f"{user.first_name} {user.last_name}".strip()
    return name if name else user.username


def _user_summary(user):
    if not user:
        return None
    return {
        "id": user.id,
        "full_name": _user_name(user),
        "role": getattr(getattr(user, "userprofile", None), "role", ""),
    }


# ─── Buffer Stock Item ──────────────────────────────────────────────────────

class BufferStockItemSerializer(serializers.ModelSerializer):
    qty_available = serializers.IntegerField(read_only=True)
    region_display = serializers.CharField(source="get_region_display", read_only=True)
    category_display = serializers.CharField(source="get_category_display", read_only=True)

    class Meta:
        model = BufferStockItem
        fields = [
            "id", "part_number", "part_name", "description",
            "category", "category_display", "brand", "region", "region_display",
            "qty_on_hand", "qty_reserved", "qty_in_transit", "qty_available",
            "reorder_level", "unit_cost", "storage_location",
            "provided_by", "last_replenished_at",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "qty_available", "created_at", "updated_at"]


# ─── OOW Approval ───────────────────────────────────────────────────────────

class OOWApprovalSerializer(serializers.ModelSerializer):
    requested_by_name = serializers.SerializerMethodField()
    approved_by_name = serializers.SerializerMethodField()
    case_number = serializers.CharField(source="buffer_case.case_number", read_only=True)
    case_type = serializers.CharField(source="buffer_case.case_type", read_only=True)
    customer_name = serializers.CharField(source="buffer_case.customer_name", read_only=True)
    part_name = serializers.CharField(source="buffer_case.part_name", read_only=True)
    region = serializers.CharField(source="buffer_case.region", read_only=True)

    class Meta:
        model = OOWApproval
        fields = [
            "id", "buffer_case", "case_number", "case_type",
            "customer_name", "part_name", "region",
            "status", "requested_by", "requested_by_name",
            "approved_by", "approved_by_name", "approver_role",
            "reason", "requested_at", "responded_at",
        ]
        read_only_fields = [
            "id", "requested_by", "approved_by",
            "approver_role", "requested_at", "responded_at",
        ]

    def get_requested_by_name(self, obj):
        return _user_name(obj.requested_by)

    def get_approved_by_name(self, obj):
        return _user_name(obj.approved_by)


# ─── Case Proof ─────────────────────────────────────────────────────────────

class CaseProofSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.SerializerMethodField()

    class Meta:
        model = CaseProof
        fields = [
            "id", "buffer_case", "proof_type", "file",
            "description", "uploaded_by", "uploaded_by_name", "uploaded_at",
        ]
        read_only_fields = ["id", "uploaded_by", "uploaded_at"]

    def get_uploaded_by_name(self, obj):
        return _user_name(obj.uploaded_by)


# ─── Replenishment Order ────────────────────────────────────────────────────

class ReplenishmentOrderSerializer(serializers.ModelSerializer):
    ordered_by_name = serializers.SerializerMethodField()
    received_by_name = serializers.SerializerMethodField()
    case_number = serializers.CharField(
        source="buffer_case.case_number", read_only=True, default="",
    )

    class Meta:
        model = ReplenishmentOrder
        fields = [
            "id", "order_number", "buffer_case", "case_number",
            "buffer_stock_item", "part_number", "part_name",
            "quantity", "region", "status",
            "ordered_by", "ordered_by_name",
            "received_by", "received_by_name",
            "order_date", "expected_delivery", "received_at",
            "notes", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "order_number", "ordered_by",
            "received_by", "created_at", "updated_at",
        ]

    def get_ordered_by_name(self, obj):
        return _user_name(obj.ordered_by)

    def get_received_by_name(self, obj):
        return _user_name(obj.received_by)


# ─── Buffer Case ────────────────────────────────────────────────────────────

class BufferCaseListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""
    case_type_display = serializers.CharField(source="get_case_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    region_display = serializers.CharField(source="get_region_display", read_only=True)
    created_by_name = serializers.SerializerMethodField()
    assigned_engineer_name = serializers.SerializerMethodField()
    approved_by_name = serializers.SerializerMethodField()

    class Meta:
        model = BufferCase
        fields = [
            "id", "case_number", "case_id", "case_type", "case_type_display",
            "status", "status_display", "region", "region_display",
            "customer_name", "customer_contact",
            "product_name", "serial_number", "model_number",
            "part_number", "part_name", "qty_used",
            "source_region",
            "assigned_engineer", "assigned_engineer_name",
            "approved_by", "approved_by_name", "approved_at",
            "proof_uploaded",
            "created_by", "created_by_name",
            "created_at", "updated_at", "closed_at",
        ]

    def get_created_by_name(self, obj):
        return _user_name(obj.created_by)

    def get_assigned_engineer_name(self, obj):
        eng = obj.assigned_engineer
        return eng.name if eng else None

    def get_approved_by_name(self, obj):
        return _user_name(obj.approved_by)


class BufferCaseDetailSerializer(BufferCaseListSerializer):
    """Full serializer including nested proof + approval + replenishment."""
    proofs = CaseProofSerializer(many=True, read_only=True)
    oow_approval = OOWApprovalSerializer(read_only=True)
    replenishment = ReplenishmentOrderSerializer(
        source="replenishment_order", read_only=True,
    )
    buffer_stock_item_detail = BufferStockItemSerializer(
        source="buffer_stock_item", read_only=True,
    )

    class Meta(BufferCaseListSerializer.Meta):
        fields = BufferCaseListSerializer.Meta.fields + [
            "customer_email", "customer_address",
            "buffer_stock_item", "buffer_stock_item_detail",
            "resolution_summary", "service_notes",
            "proofs", "oow_approval", "replenishment",
        ]


class BufferCaseWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = BufferCase
        fields = [
            "case_id", "case_type", "region",
            "customer_name", "customer_contact", "customer_email", "customer_address",
            "product_name", "serial_number", "model_number",
            "buffer_stock_item", "part_number", "part_name", "qty_used",
            "source_region",
        ]

    def validate(self, data):
        case_type = data.get("case_type", "")
        case_id = data.get("case_id", "")
        if case_type == "iw" and not case_id:
            raise serializers.ValidationError(
                {"case_id": "Case ID is required for in-warranty cases."}
            )
        return data


# ─── Inter-Region Transfer ──────────────────────────────────────────────────

class InterRegionTransferSerializer(serializers.ModelSerializer):
    requested_by_name = serializers.SerializerMethodField()
    approved_by_name = serializers.SerializerMethodField()
    received_by_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    source_region_display = serializers.CharField(
        source="get_source_region_display", read_only=True,
    )
    destination_region_display = serializers.CharField(
        source="get_destination_region_display", read_only=True,
    )

    class Meta:
        model = InterRegionTransfer
        fields = [
            "id", "transfer_number",
            "buffer_stock_item", "part_number", "part_name", "quantity",
            "source_region", "source_region_display",
            "destination_region", "destination_region_display",
            "status", "status_display",
            "related_case",
            "requested_by", "requested_by_name",
            "approved_by", "approved_by_name", "approved_at",
            "rejection_reason",
            "received_by", "received_by_name", "received_at",
            "notes", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "transfer_number",
            "requested_by", "approved_by", "approved_at",
            "received_by", "received_at",
            "created_at", "updated_at",
        ]

    def get_requested_by_name(self, obj):
        return _user_name(obj.requested_by)

    def get_approved_by_name(self, obj):
        return _user_name(obj.approved_by)

    def get_received_by_name(self, obj):
        return _user_name(obj.received_by)

    def validate(self, data):
        src = data.get("source_region", "")
        dst = data.get("destination_region", "")
        if src and dst and src == dst:
            raise serializers.ValidationError(
                {"destination_region": "Destination must differ from source region."}
            )
        return data


# ─── Audit Log ──────────────────────────────────────────────────────────────

class BufferAuditLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()
    action_display = serializers.CharField(source="get_action_display", read_only=True)

    class Meta:
        model = BufferAuditLog
        fields = [
            "id", "action", "action_display", "entity_type", "entity_id",
            "actor", "actor_name", "details", "region", "created_at",
        ]

    def get_actor_name(self, obj):
        return _user_name(obj.actor)
