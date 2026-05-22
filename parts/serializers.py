from rest_framework import serializers

from .models import PartRequest
from ticket.models import Ticket
from ticket.serializers import TicketPartRequestImageSerializer


class UserMiniSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    full_name = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()

    def get_full_name(self, obj):
        name = f"{obj.first_name} {obj.last_name}".strip()
        return name if name else obj.username

    def get_role(self, obj):
        profile = getattr(obj, 'userprofile', None)
        return profile.get_role_display() if profile else ''


class PartRequestTicketSerializer(serializers.ModelSerializer):
    part_request_images = TicketPartRequestImageSerializer(many=True, read_only=True)
    service_type_display = serializers.CharField(source="get_service_type_display", read_only=True)
    current_status_display = serializers.CharField(source="get_current_status_display", read_only=True)
    region_display = serializers.CharField(source="get_region_display", read_only=True)

    class Meta:
        model = Ticket
        fields = [
            "id",
            "ticket_number",
            "form_number",
            "work_order",
            "cust_name",
            "cust_contact",
            "cust_email",
            "cust_address",
            "location",
            "product_name",
            "serial_number",
            "model_number",
            "brand",
            "case_id",
            "condition_received",
            "service_type",
            "service_type_display",
            "priority",
            "issue_description",
            "current_status",
            "current_status_display",
            "region",
            "region_display",
            "cso_date",
            "cso_image",
            "part_request_image",
            "part_request_images",
            "created_at",
        ]


class PartRequestSerializer(serializers.ModelSerializer):
    requested_by = UserMiniSerializer(read_only=True)
    approved_by = UserMiniSerializer(read_only=True)
    ticket_number = serializers.SerializerMethodField()
    region = serializers.CharField(source='ticket.region', read_only=True)
    region_display = serializers.CharField(source='ticket.get_region_display', read_only=True)
    urgency_display = serializers.CharField(source='get_urgency_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    ticket_details = PartRequestTicketSerializer(source='ticket', read_only=True)

    class Meta:
        model = PartRequest
        fields = [
            'id', 'ticket', 'ticket_number', 'region', 'region_display',
            'requested_by',
            'part_number', 'part_name', 'description',
            'quantity', 'urgency', 'urgency_display',
            'estimated_cost', 'status', 'status_display',
            'approved_by',
            'approved_at', 'rejection_reason',
            'received_at', 'created_at', 'updated_at',
            'ticket_details',
        ]
        read_only_fields = [
            'id', 'requested_by', 'approved_by', 'approved_at',
            'rejection_reason', 'received_at', 'created_at', 'updated_at',
        ]

    def get_ticket_number(self, obj):
        ticket = obj.ticket
        return getattr(ticket, 'ticket_number', str(ticket.pk)) if ticket else None
