from rest_framework import serializers

from .models import BufferPart, BufferStock, POItem, PurchaseOrder, StockItem, StockMovement


# ─── Purchase Order ──────────────────────────────────────────────────────────

class POItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = POItem
        fields = [
            'id', 'purchase_order', 'part_request',
            'part_number', 'part_name', 'quantity',
            'unit_price', 'total', 'received_qty', 'created_at',
        ]
        read_only_fields = ['id', 'purchase_order', 'created_at']


class PurchaseOrderSerializer(serializers.ModelSerializer):
    items = POItemSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    ordered_by_name = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseOrder
        fields = [
            'id', 'po_number', 'supplier_name', 'supplier_contact',
            'supplier_email', 'status', 'status_display',
            'ordered_by', 'ordered_by_name', 'approved_by',
            'total_amount', 'order_date', 'expected_delivery',
            'actual_delivery', 'region', 'notes',
            'items', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'po_number', 'ordered_by',
            'created_at', 'updated_at',
        ]

    def get_ordered_by_name(self, obj):
        user = obj.ordered_by
        name = f"{user.first_name} {user.last_name}".strip()
        return name if name else user.username


class PurchaseOrderWriteSerializer(serializers.ModelSerializer):
    items = POItemSerializer(many=True, required=False)

    class Meta:
        model = PurchaseOrder
        fields = [
            'id', 'po_number', 'supplier_name', 'supplier_contact',
            'supplier_email', 'status', 'ordered_by', 'approved_by',
            'total_amount', 'order_date', 'expected_delivery',
            'actual_delivery', 'region', 'notes', 'items',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'po_number', 'ordered_by',
            'created_at', 'updated_at',
        ]

    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        po = PurchaseOrder.objects.create(**validated_data)
        for item_data in items_data:
            POItem.objects.create(purchase_order=po, **item_data)
        return po

    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if items_data is not None:
            instance.items.all().delete()
            for item_data in items_data:
                POItem.objects.create(purchase_order=instance, **item_data)

        return instance


# ─── Stock ───────────────────────────────────────────────────────────────────

class StockItemSerializer(serializers.ModelSerializer):
    qty_available = serializers.IntegerField(read_only=True)

    class Meta:
        model = StockItem
        fields = [
            'id', 'part_number', 'part_name', 'description',
            'category', 'brand', 'qty_on_hand', 'qty_reserved',
            'qty_on_order', 'reorder_level', 'reorder_qty',
            'unit_cost', 'region', 'storage_location',
            'qty_available', 'last_restocked_at',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'qty_available', 'created_at', 'updated_at']


class StockMovementSerializer(serializers.ModelSerializer):
    movement_type_display = serializers.CharField(
        source='get_movement_type_display', read_only=True,
    )
    performed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = StockMovement
        fields = [
            'id', 'stock_item', 'movement_type', 'movement_type_display',
            'quantity', 'reference_type', 'reference_id',
            'performed_by', 'performed_by_name', 'notes', 'created_at',
        ]
        read_only_fields = ['id', 'performed_by', 'created_at']

    def get_performed_by_name(self, obj):
        user = obj.performed_by
        name = f"{user.first_name} {user.last_name}".strip()
        return name if name else user.username


# ─── Buffer Stock ────────────────────────────────────────────────────────────

class BufferStockSerializer(serializers.ModelSerializer):
    reserved_by_name = serializers.SerializerMethodField()
    stock_item_detail = StockItemSerializer(source='stock_item', read_only=True)

    class Meta:
        model = BufferStock
        fields = [
            'id', 'stock_item', 'stock_item_detail', 'quantity',
            'reason', 'reserved_by', 'reserved_by_name',
            'reserved_for_ticket', 'is_active',
            'expires_at', 'created_at',
        ]
        read_only_fields = ['id', 'reserved_by', 'created_at']

    def get_reserved_by_name(self, obj):
        user = obj.reserved_by
        name = f"{user.first_name} {user.last_name}".strip()
        return name if name else user.username


class BufferPartSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = BufferPart
        fields = [
            "id", "part_number", "part_name", "quantity", "general_name",
            "created_by", "created_by_name", "created_at",
        ]
        read_only_fields = ["id", "created_by", "created_at"]

    def get_created_by_name(self, obj):
        if obj.created_by:
            name = f"{obj.created_by.first_name} {obj.created_by.last_name}".strip()
            return name if name else obj.created_by.username
        return None
