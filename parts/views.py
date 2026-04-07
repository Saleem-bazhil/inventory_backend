import math

from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PartRequest
from .serializers import PartRequestSerializer


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


class PartRequestListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = PartRequest.objects.select_related('requested_by', 'approved_by', 'ticket').all()

        ticket_id = request.query_params.get('ticket_id')
        if ticket_id:
            qs = qs.filter(ticket_id=ticket_id)

        status_filter = request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        urgency = request.query_params.get('urgency')
        if urgency:
            qs = qs.filter(urgency=urgency)

        page_qs, meta = paginate_queryset(qs, request)
        serializer = PartRequestSerializer(page_qs, many=True)
        return Response({
            'items': serializer.data,
            **meta,
        })

    def post(self, request):
        serializer = PartRequestSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(requested_by=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PartRequestDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _get_object(self, pk):
        try:
            return PartRequest.objects.select_related(
                'requested_by', 'approved_by', 'ticket',
            ).get(pk=pk)
        except PartRequest.DoesNotExist:
            return None

    def get(self, request, pk):
        obj = self._get_object(pk)
        if not obj:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = PartRequestSerializer(obj)
        return Response(serializer.data)

    def put(self, request, pk):
        obj = self._get_object(pk)
        if not obj:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = PartRequestSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PartRequestApproveView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            obj = PartRequest.objects.get(pk=pk)
        except PartRequest.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        if obj.status != 'pending':
            return Response(
                {'detail': f'Cannot approve a request with status "{obj.get_status_display()}".'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        obj.status = 'approved'
        obj.approved_by = request.user
        obj.approved_at = timezone.now()
        obj.save()

        serializer = PartRequestSerializer(obj)
        return Response(serializer.data)


class PartRequestRejectView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            obj = PartRequest.objects.get(pk=pk)
        except PartRequest.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        if obj.status != 'pending':
            return Response(
                {'detail': f'Cannot reject a request with status "{obj.get_status_display()}".'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        rejection_reason = request.data.get('rejection_reason', '')
        if not rejection_reason:
            return Response(
                {'detail': 'rejection_reason is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        obj.status = 'rejected'
        obj.approved_by = request.user
        obj.approved_at = timezone.now()
        obj.rejection_reason = rejection_reason
        obj.save()

        serializer = PartRequestSerializer(obj)
        return Response(serializer.data)


class PendingPartRequestsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = PartRequest.objects.select_related(
            'requested_by', 'approved_by', 'ticket',
        ).filter(status='pending')

        page_qs, meta = paginate_queryset(qs, request)
        serializer = PartRequestSerializer(page_qs, many=True)
        return Response({
            'items': serializer.data,
            **meta,
        })
