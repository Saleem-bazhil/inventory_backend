import math

from django.db.models import Q
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import BufferPart, BufferStock, POItem, PurchaseOrder, StockItem, StockMovement
from .serializers import (
    BufferPartSerializer,
    BufferStockSerializer,
    POItemSerializer,
    PurchaseOrderSerializer,
    PurchaseOrderWriteSerializer,
    StockItemSerializer,
    StockMovementSerializer,
)


def paginate_queryset(queryset, request):
    """Shared pagination helper. Returns (page_qs, meta_dict)."""
    try:
        page = max(int(request.query_params.get('page', 1)), 1)
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = min(max(int(request.query_params.get('per_page', 20)), 1), 100)
    except (TypeError, ValueError):
        per_page = 20

    total = queryset.count()
    pages = math.ceil(total / per_page) if total else 1
    start = (page - 1) * per_page
    end = start + per_page

    return queryset[start:end], {
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': pages,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Purchase Orders
# ═══════════════════════════════════════════════════════════════════════════════

class POListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = PurchaseOrder.objects.select_related('ordered_by').prefetch_related('items').all()

        status_filter = request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        region = request.query_params.get('region')
        if region:
            qs = qs.filter(region=region)

        page_qs, meta = paginate_queryset(qs, request)
        serializer = PurchaseOrderSerializer(page_qs, many=True)
        return Response({
            'items': serializer.data,
            **meta,
        })

    def post(self, request):
        serializer = PurchaseOrderWriteSerializer(data=request.data)
        if serializer.is_valid():
            po = serializer.save(ordered_by=request.user)
            return Response(
                PurchaseOrderSerializer(po).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PODetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _get_object(self, pk):
        try:
            return PurchaseOrder.objects.select_related(
                'ordered_by',
            ).prefetch_related('items').get(pk=pk)
        except PurchaseOrder.DoesNotExist:
            return None

    def get(self, request, pk):
        obj = self._get_object(pk)
        if not obj:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = PurchaseOrderSerializer(obj)
        return Response(serializer.data)

    def put(self, request, pk):
        obj = self._get_object(pk)
        if not obj:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = PurchaseOrderWriteSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            po = serializer.save()
            return Response(PurchaseOrderSerializer(po).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class POSendView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            obj = PurchaseOrder.objects.get(pk=pk)
        except PurchaseOrder.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        if obj.status != 'draft':
            return Response(
                {'detail': f'Cannot send a PO with status "{obj.get_status_display()}".'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        obj.status = 'sent'
        obj.order_date = timezone.now().date()
        obj.save()

        serializer = PurchaseOrderSerializer(obj)
        return Response(serializer.data)


class POReceiveView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            po = PurchaseOrder.objects.prefetch_related('items').get(pk=pk)
        except PurchaseOrder.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        items_data = request.data.get('items', [])
        if not items_data:
            return Response(
                {'detail': 'items list is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        for item_info in items_data:
            po_item_id = item_info.get('po_item_id')
            received_qty = item_info.get('received_qty', 0)
            try:
                po_item = POItem.objects.get(pk=po_item_id, purchase_order=po)
            except POItem.DoesNotExist:
                return Response(
                    {'detail': f'PO item {po_item_id} not found.'},
                    status=status.HTTP_404_NOT_FOUND,
                )
            po_item.received_qty = received_qty
            po_item.save()

        # Determine PO status based on received quantities
        all_items = po.items.all()
        all_received = all(item.received_qty >= item.quantity for item in all_items)
        any_received = any(item.received_qty > 0 for item in all_items)

        if all_received:
            po.status = 'received'
            po.actual_delivery = timezone.now().date()
        elif any_received:
            po.status = 'partial_received'

        po.save()

        serializer = PurchaseOrderSerializer(po)
        return Response(serializer.data)


# ═══════════════════════════════════════════════════════════════════════════════
# Stock
# ═══════════════════════════════════════════════════════════════════════════════

class StockListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = StockItem.objects.all()

        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(part_number__icontains=search)
                | Q(part_name__icontains=search)
                | Q(description__icontains=search)
            )

        category = request.query_params.get('category')
        if category:
            qs = qs.filter(category=category)

        region = request.query_params.get('region')
        if region:
            qs = qs.filter(region=region)

        low_stock_only = request.query_params.get('low_stock_only')
        if low_stock_only and low_stock_only.lower() in ('true', '1', 'yes'):
            from django.db.models import F
            qs = qs.filter(qty_on_hand__lte=F('reorder_level'))

        page_qs, meta = paginate_queryset(qs, request)
        serializer = StockItemSerializer(page_qs, many=True)
        return Response({
            'items': serializer.data,
            **meta,
        })

    def post(self, request):
        serializer = StockItemSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class StockDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _get_object(self, pk):
        try:
            return StockItem.objects.get(pk=pk)
        except StockItem.DoesNotExist:
            return None

    def get(self, request, pk):
        obj = self._get_object(pk)
        if not obj:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = StockItemSerializer(obj)
        return Response(serializer.data)

    def put(self, request, pk):
        obj = self._get_object(pk)
        if not obj:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = StockItemSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        obj = self._get_object(pk)
        if not obj:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class StockMovementsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        try:
            stock_item = StockItem.objects.get(pk=pk)
        except StockItem.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        qs = StockMovement.objects.filter(stock_item=stock_item).select_related('performed_by')
        page_qs, meta = paginate_queryset(qs, request)
        serializer = StockMovementSerializer(page_qs, many=True)
        return Response({
            'items': serializer.data,
            **meta,
        })


class StockReserveView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            stock_item = StockItem.objects.get(pk=pk)
        except StockItem.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        quantity = request.data.get('quantity', 0)
        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            return Response(
                {'detail': 'quantity must be an integer.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if quantity <= 0:
            return Response(
                {'detail': 'quantity must be positive.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        available = stock_item.qty_on_hand - stock_item.qty_reserved
        if quantity > available:
            return Response(
                {'detail': f'Only {available} available for reservation.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        stock_item.qty_reserved += quantity
        stock_item.save()

        StockMovement.objects.create(
            stock_item=stock_item,
            movement_type='reserved',
            quantity=quantity,
            performed_by=request.user,
            notes=request.data.get('notes', ''),
        )

        serializer = StockItemSerializer(stock_item)
        return Response(serializer.data)


class StockReleaseView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            stock_item = StockItem.objects.get(pk=pk)
        except StockItem.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        quantity = request.data.get('quantity', 0)
        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            return Response(
                {'detail': 'quantity must be an integer.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if quantity <= 0:
            return Response(
                {'detail': 'quantity must be positive.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if quantity > stock_item.qty_reserved:
            return Response(
                {'detail': f'Only {stock_item.qty_reserved} reserved to release.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        stock_item.qty_reserved -= quantity
        stock_item.save()

        StockMovement.objects.create(
            stock_item=stock_item,
            movement_type='released',
            quantity=quantity,
            performed_by=request.user,
            notes=request.data.get('notes', ''),
        )

        serializer = StockItemSerializer(stock_item)
        return Response(serializer.data)


class StockAdjustView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        stock_item_id = request.data.get('stock_item_id')
        quantity = request.data.get('quantity')
        notes = request.data.get('notes', '')

        if not stock_item_id or quantity is None:
            return Response(
                {'detail': 'stock_item_id and quantity are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            return Response(
                {'detail': 'quantity must be an integer.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            stock_item = StockItem.objects.get(pk=stock_item_id)
        except StockItem.DoesNotExist:
            return Response({'detail': 'Stock item not found.'}, status=status.HTTP_404_NOT_FOUND)

        stock_item.qty_on_hand += quantity
        if stock_item.qty_on_hand < 0:
            stock_item.qty_on_hand = 0
        stock_item.save()

        StockMovement.objects.create(
            stock_item=stock_item,
            movement_type='adjustment',
            quantity=quantity,
            performed_by=request.user,
            notes=notes,
        )

        serializer = StockItemSerializer(stock_item)
        return Response(serializer.data)


class LowStockView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from django.db.models import F
        qs = StockItem.objects.filter(qty_on_hand__lte=F('reorder_level'))

        page_qs, meta = paginate_queryset(qs, request)
        serializer = StockItemSerializer(page_qs, many=True)
        return Response({
            'items': serializer.data,
            **meta,
        })


class StockSearchView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        q = request.query_params.get('q', '').strip()
        if not q:
            return Response({'items': [], 'total': 0, 'page': 1, 'per_page': 20, 'pages': 1})

        qs = StockItem.objects.filter(
            Q(part_number__icontains=q)
            | Q(part_name__icontains=q)
            | Q(description__icontains=q)
            | Q(category__icontains=q)
            | Q(brand__icontains=q)
        )

        page_qs, meta = paginate_queryset(qs, request)
        serializer = StockItemSerializer(page_qs, many=True)
        return Response({
            'items': serializer.data,
            **meta,
        })


# ═══════════════════════════════════════════════════════════════════════════════
# Buffer Stock
# ═══════════════════════════════════════════════════════════════════════════════

class BufferListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = BufferStock.objects.select_related(
            'stock_item', 'reserved_by',
        ).filter(is_active=True)

        page_qs, meta = paginate_queryset(qs, request)
        serializer = BufferStockSerializer(page_qs, many=True)
        return Response({
            'items': serializer.data,
            **meta,
        })

    def post(self, request):
        serializer = BufferStockSerializer(data=request.data)
        if serializer.is_valid():
            buffer = serializer.save(reserved_by=request.user)

            # Record stock movement
            stock_item = buffer.stock_item
            stock_item.qty_reserved += buffer.quantity
            stock_item.save()

            StockMovement.objects.create(
                stock_item=stock_item,
                movement_type='buffer_in',
                quantity=buffer.quantity,
                reference_type='buffer_stock',
                reference_id=buffer.pk,
                performed_by=request.user,
                notes=buffer.reason,
            )

            return Response(
                BufferStockSerializer(buffer).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class BufferUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, pk):
        try:
            obj = BufferStock.objects.get(pk=pk)
        except BufferStock.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = BufferStockSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class BufferReleaseView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        try:
            obj = BufferStock.objects.select_related('stock_item').get(pk=pk)
        except BufferStock.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        if not obj.is_active:
            return Response(
                {'detail': 'Buffer is already released.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Release reserved quantity back
        stock_item = obj.stock_item
        stock_item.qty_reserved = max(0, stock_item.qty_reserved - obj.quantity)
        stock_item.save()

        StockMovement.objects.create(
            stock_item=stock_item,
            movement_type='buffer_out',
            quantity=obj.quantity,
            reference_type='buffer_stock',
            reference_id=obj.pk,
            performed_by=request.user,
            notes=f'Buffer released: {obj.reason}',
        )

        obj.is_active = False
        obj.save()

        return Response({'detail': 'Buffer released successfully.'}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Buffer Parts (simple standalone buffer)
# ---------------------------------------------------------------------------

def _can_pick_any_region(user):
    """Admin / super_admin / manager can pick any region for buffer parts."""
    profile = getattr(user, "userprofile", None)
    if not profile:
        return False
    return profile.role in ("admin", "super_admin", "manager")


class BufferPartListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = BufferPart.objects.all()

        profile = getattr(request.user, "userprofile", None)
        user_region = profile.region if profile else None
        view_mode = request.query_params.get("view", "").strip()
        region_filter = request.query_params.get("region", "").strip()

        if region_filter:
            qs = qs.filter(region=region_filter)
        elif view_mode == "my_region" and user_region:
            qs = qs.filter(region=user_region)
        # view_mode == "overall" or unset: no region filter — everyone sees all

        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(part_number__icontains=search)
                | Q(part_name__icontains=search)
                | Q(general_name__icontains=search)
            )
        page_qs, meta = paginate_queryset(qs, request)
        serializer = BufferPartSerializer(page_qs, many=True)
        return Response({"items": serializer.data, **meta})

    def post(self, request):
        profile = getattr(request.user, "userprofile", None)
        serializer = BufferPartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if _can_pick_any_region(request.user):
            region = serializer.validated_data.get("region", "")
            if not region:
                return Response(
                    {"region": ["This field is required."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            if not profile or not profile.region:
                return Response(
                    {"detail": "Your account has no region assigned."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            serializer.validated_data["region"] = profile.region

        serializer.save(created_by=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class BufferPartDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        try:
            obj = BufferPart.objects.get(pk=pk)
        except BufferPart.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(BufferPartSerializer(obj).data)

    def put(self, request, pk):
        try:
            obj = BufferPart.objects.get(pk=pk)
        except BufferPart.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        profile = getattr(request.user, "userprofile", None)
        if not _can_pick_any_region(request.user):
            if not profile or not profile.region or obj.region != profile.region:
                return Response(
                    {"detail": "You can only edit buffer parts in your own region."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        serializer = BufferPartSerializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        if not _can_pick_any_region(request.user) and "region" in serializer.validated_data:
            serializer.validated_data["region"] = obj.region

        serializer.save()
        return Response(BufferPartSerializer(obj).data)

    def delete(self, request, pk):
        try:
            obj = BufferPart.objects.get(pk=pk)
        except BufferPart.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        profile = getattr(request.user, "userprofile", None)
        if not _can_pick_any_region(request.user):
            if not profile or not profile.region or obj.region != profile.region:
                return Response(
                    {"detail": "You can only delete buffer parts in your own region."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Buffer Parts — Summary (region-wise totals)
# ---------------------------------------------------------------------------

class BufferPartSummaryView(APIView):
    """
    GET /api/buffer-parts/summary/
    Returns region-wise quantity totals and an overall total.
    - super_admin / manager → all regions
    - sub_admin → only their own region
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from django.db.models import Sum

        qs = BufferPart.objects.all()

        # Use the same view/region logic as the list endpoint
        profile = getattr(request.user, "userprofile", None)
        user_region = profile.region if profile else None
        view_mode = request.query_params.get("view", "").strip()
        region_filter = request.query_params.get("region", "").strip()

        if region_filter:
            qs = qs.filter(region=region_filter)
        elif view_mode == "my_region" and user_region:
            qs = qs.filter(region=user_region)
        # view_mode == "overall" or unset: no region filter

        regions = (
            qs.values("region")
            .annotate(total=Sum("quantity"))
            .order_by("region")
        )

        region_list = [
            {"region": r["region"] or "unassigned", "total": r["total"] or 0}
            for r in regions
        ]
        grand_total = sum(r["total"] for r in region_list)

        return Response({
            "regions": region_list,
            "total": grand_total,
        })

