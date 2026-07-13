from rest_framework import serializers
from .models import HPStockItem, HPStockRMAPart, OpencallPartsCount

class HPStockItemSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    # Price matched from the HP Stock RMA Part catalog by good_part_number == part_number.
    price = serializers.SerializerMethodField()

    class Meta:
        model = HPStockItem
        fields = '__all__'
        read_only_fields = ('created_by', 'created_at', 'updated_at', 'transition_history')

    def _is_super_admin(self):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        profile = getattr(user, 'userprofile', None)
        return getattr(profile, 'role', '') == 'super_admin'

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Price is super-admin-only, so it must not reach anyone else's payload.
        if not self._is_super_admin():
            data.pop('price', None)
        return data

    def get_price(self, obj):
        if not self._is_super_admin():
            return None
        good_part = (obj.good_part_number or '').strip()
        if not good_part:
            return None
        price = (
            HPStockRMAPart.objects
            .filter(part_number=good_part)
            .values_list('price', flat=True)
            .first()
        )
        return float(price) if price is not None else None

    def create(self, validated_data):
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['created_by'] = request.user
        return super().create(validated_data)


class HPStockRMAPartSerializer(serializers.ModelSerializer):
    class Meta:
        model = HPStockRMAPart
        fields = '__all__'


class OpencallPartsCountSerializer(serializers.ModelSerializer):
    class Meta:
        model = OpencallPartsCount
        fields = ('id', 'report_date', 'region', 'count', 'updated_at')
