from rest_framework import serializers
from .models import HPStockItem, HPStockRMAPart

class HPStockItemSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)

    class Meta:
        model = HPStockItem
        fields = '__all__'
        read_only_fields = ('created_by', 'created_at', 'updated_at', 'transition_history')

    def create(self, validated_data):
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['created_by'] = request.user
        return super().create(validated_data)


class HPStockRMAPartSerializer(serializers.ModelSerializer):
    class Meta:
        model = HPStockRMAPart
        fields = '__all__'
