import math

from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Invoice
from .serializers import InvoiceSerializer, InvoiceWriteSerializer


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


class InvoiceListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = Invoice.objects.select_related('created_by', 'ticket').prefetch_related('items').all()

        ticket_id = request.query_params.get('ticket_id')
        if ticket_id:
            qs = qs.filter(ticket_id=ticket_id)

        status_filter = request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        region = request.query_params.get('region')
        if region:
            qs = qs.filter(region=region)

        page_qs, meta = paginate_queryset(qs, request)
        serializer = InvoiceSerializer(page_qs, many=True)
        return Response({
            'items': serializer.data,
            **meta,
        })

    def post(self, request):
        serializer = InvoiceWriteSerializer(data=request.data)
        if serializer.is_valid():
            invoice = serializer.save(created_by=request.user)
            return Response(
                InvoiceSerializer(invoice).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class InvoiceDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _get_object(self, pk):
        try:
            return Invoice.objects.select_related(
                'created_by', 'ticket',
            ).prefetch_related('items').get(pk=pk)
        except Invoice.DoesNotExist:
            return None

    def get(self, request, pk):
        obj = self._get_object(pk)
        if not obj:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = InvoiceSerializer(obj)
        return Response(serializer.data)

    def put(self, request, pk):
        obj = self._get_object(pk)
        if not obj:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = InvoiceWriteSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            invoice = serializer.save()
            return Response(InvoiceSerializer(invoice).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SendInvoiceView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            obj = Invoice.objects.get(pk=pk)
        except Invoice.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        if obj.status != 'draft':
            return Response(
                {'detail': f'Cannot send an invoice with status "{obj.get_status_display()}".'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        obj.status = 'sent'
        obj.save()

        serializer = InvoiceSerializer(obj)
        return Response(serializer.data)


class MarkPaidView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            obj = Invoice.objects.get(pk=pk)
        except Invoice.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        payment_method = request.data.get('payment_method', '')
        paid_amount = request.data.get('paid_amount')

        if paid_amount is None:
            return Response(
                {'detail': 'paid_amount is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            from decimal import Decimal
            paid_amount = Decimal(str(paid_amount))
        except Exception:
            return Response(
                {'detail': 'paid_amount must be a valid number.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        obj.payment_method = payment_method
        obj.paid_amount = paid_amount
        obj.paid_at = timezone.now()

        if paid_amount >= obj.total:
            obj.status = 'paid'
        else:
            obj.status = 'partial'

        obj.save()

        serializer = InvoiceSerializer(obj)
        return Response(serializer.data)
