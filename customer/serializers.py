from rest_framework import serializers

from .models import Customer


class CustomerSerializer(serializers.ModelSerializer):
    total_transactions = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = [
            "id",
            "name",
            "email",
            "phone",
            "company",
            "total_transactions",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_total_transactions(self, obj):
        return 0
