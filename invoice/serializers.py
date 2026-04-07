from rest_framework import serializers

from .models import Invoice, InvoiceItem


class InvoiceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceItem
        fields = [
            'id', 'invoice', 'description',
            'quantity', 'unit_price', 'total',
        ]
        read_only_fields = ['id', 'invoice']


class InvoiceSerializer(serializers.ModelSerializer):
    items = InvoiceItemSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    created_by_name = serializers.SerializerMethodField()
    ticket_number = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = [
            'id', 'invoice_number', 'ticket', 'ticket_number',
            'quotation', 'customer_name', 'customer_phone',
            'customer_email', 'customer_address',
            'subtotal', 'tax_percent', 'tax_amount',
            'discount', 'total', 'status', 'status_display',
            'payment_method', 'paid_amount', 'paid_at',
            'due_date', 'created_by', 'created_by_name',
            'region', 'notes', 'items',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'invoice_number', 'created_by',
            'paid_at', 'created_at', 'updated_at',
        ]

    def get_created_by_name(self, obj):
        user = obj.created_by
        name = f"{user.first_name} {user.last_name}".strip()
        return name if name else user.username

    def get_ticket_number(self, obj):
        ticket = obj.ticket
        return getattr(ticket, 'ticket_number', str(ticket.pk)) if ticket else None


class InvoiceWriteSerializer(serializers.ModelSerializer):
    items = InvoiceItemSerializer(many=True, required=False)

    class Meta:
        model = Invoice
        fields = [
            'id', 'invoice_number', 'ticket', 'quotation',
            'customer_name', 'customer_phone', 'customer_email',
            'customer_address', 'subtotal', 'tax_percent',
            'tax_amount', 'discount', 'total', 'status',
            'payment_method', 'due_date', 'created_by',
            'region', 'notes', 'items',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'invoice_number', 'created_by',
            'created_at', 'updated_at',
        ]

    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        invoice = Invoice.objects.create(**validated_data)
        for item_data in items_data:
            InvoiceItem.objects.create(invoice=invoice, **item_data)
        return invoice

    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if items_data is not None:
            instance.items.all().delete()
            for item_data in items_data:
                InvoiceItem.objects.create(invoice=instance, **item_data)

        return instance
