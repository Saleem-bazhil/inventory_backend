from rest_framework import serializers

from .models import PartRequest


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


class PartRequestSerializer(serializers.ModelSerializer):
    requested_by_detail = UserMiniSerializer(source='requested_by', read_only=True)
    approved_by_detail = UserMiniSerializer(source='approved_by', read_only=True)
    ticket_number = serializers.SerializerMethodField()
    urgency_display = serializers.CharField(source='get_urgency_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = PartRequest
        fields = [
            'id', 'ticket', 'ticket_number',
            'requested_by', 'requested_by_detail',
            'part_number', 'part_name', 'description',
            'quantity', 'urgency', 'urgency_display',
            'estimated_cost', 'status', 'status_display',
            'approved_by', 'approved_by_detail',
            'approved_at', 'rejection_reason',
            'received_at', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'requested_by', 'approved_by', 'approved_at',
            'rejection_reason', 'received_at', 'created_at', 'updated_at',
        ]

    def get_ticket_number(self, obj):
        ticket = obj.ticket
        return getattr(ticket, 'ticket_number', str(ticket.pk)) if ticket else None
