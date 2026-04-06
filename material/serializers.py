from rest_framework import serializers
from .models import MaterialTrack


class MaterialSerializer(serializers.ModelSerializer):
    region_display = serializers.CharField(source="get_region_display", read_only=True)
    service_type_display = serializers.CharField(source="get_service_type_display", read_only=True)
    call_status_display = serializers.CharField(source="get_call_status_display", read_only=True)

    class Meta:
        model = MaterialTrack
        fields = "__all__"
        read_only_fields = ["user", "region", "created_at", "updated_at"]
