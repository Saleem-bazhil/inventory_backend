from rest_framework import serializers

from ticket.models import Ticket


class CustomerSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="cust_name", allow_blank=True, required=False)
    email = serializers.CharField(source="cust_email", allow_blank=True, required=False, allow_null=True)
    phone = serializers.CharField(source="cust_contact", allow_blank=True, required=False, allow_null=True)
    company = serializers.CharField(source="work_order", allow_blank=True, required=False)
    total_transactions = serializers.SerializerMethodField()
    status = serializers.CharField(source="current_status", read_only=True)

    class Meta:
        model = Ticket
        fields = [
            "id",
            "name",
            "email",
            "phone",
            "company",
            "total_transactions",
            "created_at",
            "region",
            "status",
            "ticket_number",
            "form_number",
        ]
        read_only_fields = ["id", "created_at"]

    def get_total_transactions(self, obj):
        if obj.cust_contact:
            return Ticket.objects.filter(cust_contact=obj.cust_contact).count()
        return 1

