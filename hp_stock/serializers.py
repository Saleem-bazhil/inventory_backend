from django.utils import timezone
from rest_framework import serializers
from .models import (
    HPStockItem, HPStockRMAPart, OpencallPartsCount, HPStockSettings,
    RECEIVED, SOURCE_FLEX, SOURCE_MANUAL,
)

class HPStockItemSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    part_received_by_name = serializers.CharField(
        source='part_received_by.get_full_name', read_only=True, default='',
    )
    # Price matched from the HP Stock RMA Part catalog by good_part_number == part_number.
    price = serializers.SerializerMethodField()

    class Meta:
        model = HPStockItem
        fields = '__all__'
        read_only_fields = (
            'created_by', 'created_at', 'updated_at', 'transition_history',
            'part_received_by',
        )

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
        """Create, stamping a hand-keyed row as already received.

        Who is creating this? The OpenCall sync always sends
        `part_received_status`, even as '' when Flex said nothing; the HP Stock
        form never sends the key at all. So an absent key means a person is
        entering a part they are physically holding - stamp it RECEIVED, or the
        received-only filter would hide the row the moment they saved it. A key
        that is present is honoured exactly as sent, blank included.
        """
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['created_by'] = request.user

        if 'part_received_status' not in validated_data:
            validated_data['part_received_status'] = RECEIVED
            validated_data['part_received_source'] = SOURCE_MANUAL
            validated_data['part_received_at'] = timezone.now()
        elif validated_data.get('part_received_status') == RECEIVED:
            validated_data.setdefault('part_received_at', timezone.now())
            validated_data.setdefault('part_received_source', SOURCE_FLEX)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        """Enforce the sticky rule: a received spare never becomes un-received.

        The OpenCall sync pushes whatever the newest Flex export says on every
        15-minute cycle, and a case that closes in Flex keeps re-serving its last
        (possibly stale) part lines forever. Without this guard that could walk a
        part back to in-transit and hide a row somebody is working on. Enforcing
        it here rather than in the sync means the invariant holds for every
        caller, and the sync gets to stay dumb.
        """
        incoming = validated_data.get('part_received_status')
        already_received = instance.part_received_status == RECEIVED

        if already_received and incoming is not None and incoming != RECEIVED:
            # Keep the raw Flex value (flex_installed_status) - that mismatch is
            # exactly what the reconciliation view is for - but drop the downgrade.
            validated_data.pop('part_received_status', None)
            validated_data.pop('part_received_source', None)
            validated_data.pop('part_received_at', None)
        elif incoming == RECEIVED and not already_received:
            validated_data.setdefault('part_received_at', timezone.now())
            validated_data.setdefault('part_received_source', SOURCE_FLEX)

        return super().update(instance, validated_data)


class HPStockRMAPartSerializer(serializers.ModelSerializer):
    class Meta:
        model = HPStockRMAPart
        fields = '__all__'


class OpencallPartsCountSerializer(serializers.ModelSerializer):
    class Meta:
        model = OpencallPartsCount
        fields = ('id', 'report_date', 'region', 'count', 'updated_at')


class HPStockSettingsSerializer(serializers.ModelSerializer):
    updated_by_name = serializers.CharField(
        source='updated_by.get_full_name', read_only=True, default='',
    )

    class Meta:
        model = HPStockSettings
        fields = ('received_spare_only', 'updated_by_name', 'updated_at')
        read_only_fields = ('updated_by_name', 'updated_at')
