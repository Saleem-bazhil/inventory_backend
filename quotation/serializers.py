from rest_framework import serializers

from .models import Quotation, QuotationItem


class QuotationItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuotationItem
        fields = [
            'id', 'quotation', 'part_request',
            'description', 'quantity', 'unit_price', 'total',
            'created_at',
        ]
        read_only_fields = ['id', 'quotation', 'created_at']


class QuotationSerializer(serializers.ModelSerializer):
    items = QuotationItemSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    prepared_by_name = serializers.SerializerMethodField()
    ticket_number = serializers.SerializerMethodField()

    class Meta:
        model = Quotation
        fields = [
            'id', 'quotation_number', 'ticket', 'ticket_number',
            'parts_cost', 'labor_cost', 'tax_percent', 'tax_amount',
            'discount', 'total_amount', 'status', 'status_display',
            'prepared_by', 'prepared_by_name', 'approved_by',
            'sent_at', 'customer_response_at', 'valid_until',
            'notes', 'rejection_reason',
            'items', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'quotation_number', 'prepared_by',
            'sent_at', 'customer_response_at',
            'created_at', 'updated_at',
        ]

    def get_prepared_by_name(self, obj):
        user = obj.prepared_by
        name = f"{user.first_name} {user.last_name}".strip()
        return name if name else user.username

    def get_ticket_number(self, obj):
        ticket = obj.ticket
        return getattr(ticket, 'ticket_number', str(ticket.pk)) if ticket else None


class QuotationWriteSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating quotations with nested items."""
    items = QuotationItemSerializer(many=True, required=False)

    class Meta:
        model = Quotation
        fields = [
            'id', 'quotation_number', 'ticket',
            'parts_cost', 'labor_cost', 'tax_percent', 'tax_amount',
            'discount', 'total_amount', 'status',
            'prepared_by', 'approved_by',
            'valid_until', 'notes', 'rejection_reason',
            'items', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'quotation_number', 'prepared_by',
            'created_at', 'updated_at',
        ]

    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        quotation = Quotation.objects.create(**validated_data)
        for item_data in items_data:
            QuotationItem.objects.create(quotation=quotation, **item_data)
        return quotation

    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if items_data is not None:
            instance.items.all().delete()
            for item_data in items_data:
                QuotationItem.objects.create(quotation=instance, **item_data)

        return instance
