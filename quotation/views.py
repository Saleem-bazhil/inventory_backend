import math

from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Quotation
from .serializers import QuotationSerializer, QuotationWriteSerializer


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


class QuotationListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        profile = getattr(user, "userprofile", None)
        role = profile.role if profile else "admin"
        
        # Only 'super_admin' and 'admin' can see all data across regions
        is_global_admin = role in ('super_admin', 'admin')

        qs = Quotation.objects.select_related('prepared_by', 'ticket').prefetch_related('items')
        
        if not is_global_admin:
            if profile and profile.region:
                qs = qs.filter(ticket__region=profile.region)
            else:
                # Fallback: at least ensure only what they created is seen if orphan profile
                qs = qs.filter(prepared_by=user)
        
        qs = qs.all()

        ticket_id = request.query_params.get('ticket_id')
        if ticket_id:
            qs = qs.filter(ticket_id=ticket_id)

        status_filter = request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        region_filter = request.query_params.get('region')
        # Only allow region override if global admin
        if region_filter and is_global_admin:
            qs = qs.filter(ticket__region=region_filter)

        page_qs, meta = paginate_queryset(qs, request)
        serializer = QuotationSerializer(page_qs, many=True)
        return Response({
            'items': serializer.data,
            **meta,
        })

    def post(self, request):
        serializer = QuotationWriteSerializer(data=request.data)
        if serializer.is_valid():
            quotation = serializer.save(prepared_by=request.user)
            return Response(
                QuotationSerializer(quotation).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class QuotationDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _get_object(self, pk):
        try:
            return Quotation.objects.select_related(
                'prepared_by', 'ticket',
            ).prefetch_related('items').get(pk=pk)
        except Quotation.DoesNotExist:
            return None

    def get(self, request, pk):
        obj = self._get_object(pk)
        if not obj:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = QuotationSerializer(obj)
        return Response(serializer.data)

    def put(self, request, pk):
        obj = self._get_object(pk)
        if not obj:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = QuotationWriteSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            quotation = serializer.save()
            return Response(QuotationSerializer(quotation).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SendQuotationView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            obj = Quotation.objects.get(pk=pk)
        except Quotation.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        if obj.status not in ('draft',):
            return Response(
                {'detail': f'Cannot send a quotation with status "{obj.get_status_display()}".'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        obj.status = 'sent'
        obj.sent_at = timezone.now()
        obj.save()

        serializer = QuotationSerializer(obj)
        return Response(serializer.data)


class CustomerResponseView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            obj = Quotation.objects.get(pk=pk)
        except Quotation.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        response_value = request.data.get('response')
        if response_value not in ('approved', 'rejected'):
            return Response(
                {'detail': 'response must be "approved" or "rejected".'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if response_value == 'approved':
            obj.status = 'customer_approved'
        else:
            obj.status = 'customer_rejected'
            obj.rejection_reason = request.data.get('reason', '')

        obj.customer_response_at = timezone.now()
        obj.save()

        serializer = QuotationSerializer(obj)
        return Response(serializer.data)


class QuotationSummaryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from django.db.models import Count
        from authenticate.models import UserProfile

        user = request.user
        profile = getattr(user, "userprofile", None)
        role = profile.role if profile else "admin"
        
        is_global_admin = role in ('super_admin', 'admin')
        
        qs = Quotation.objects.all()
        if not is_global_admin:
            if profile and profile.region:
                qs = qs.filter(ticket__region=profile.region)

        region_list = []
        
        # Define subset to iterate: if not admin, ONLY iterate their own region
        choices_to_check = UserProfile.REGION_CHOICES
        if not is_global_admin and profile and profile.region:
             # only keep their region
             choices_to_check = [c for c in UserProfile.REGION_CHOICES if c[0] == profile.region]

        for code, label in choices_to_check:
            count = qs.filter(ticket__region=code).count()
            region_list.append({
                'region': code,
                'total': count
            })
        
        grand_total = qs.count()

        return Response({
            'regions': region_list,
            'total': grand_total,
        })
