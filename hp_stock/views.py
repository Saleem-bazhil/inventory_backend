from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db.models import Count, Q
from .models import HPStockItem
from .serializers import HPStockItemSerializer

from rest_framework.pagination import PageNumberPagination
import math

class CustomPageNumberPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'per_page'
    max_page_size = 100

    def get_paginated_response(self, data):
        total = self.page.paginator.count
        per_page = self.get_page_size(self.request)
        pages = math.ceil(total / per_page) if total else 1
        return Response({
            'items': data,
            'total': total,
            'page': self.page.number,
            'per_page': per_page,
            'pages': pages
        })

class HPStockItemViewSet(viewsets.ModelViewSet):
    queryset = HPStockItem.objects.all()
    serializer_class = HPStockItemSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        profile = getattr(user, 'userprofile', None)
        
        # Admin roles see all by default unless filtered, others see their region
        role = profile.role if profile else ''
        if role not in ['admin', 'super_admin', 'manager']:
            user_region = profile.region if profile else ''
            if user_region:
                queryset = queryset.filter(region=user_region)

        # Filters
        view_mode = self.request.query_params.get('view', '')
        search = self.request.query_params.get('search', '')
        region = self.request.query_params.get('region', '')

        if region and region != 'all':
            # Non-admins should not be able to bypass their region check
            if role not in ['admin', 'super_admin', 'manager']:
                user_region = profile.region if profile else ''
                queryset = queryset.filter(region=user_region)
            else:
                queryset = queryset.filter(region=region)
        elif view_mode == 'my_region':
            user_region = profile.region if profile else ''
            if user_region:
                queryset = queryset.filter(region=user_region)

        if search:
            queryset = queryset.filter(
                Q(case_id__icontains=search) |
                Q(work_order_id__icontains=search) |
                Q(delivery_no__icontains=search) |
                Q(service_event_no__icontains=search) |
                Q(material_order_no__icontains=search) |
                Q(hp_sales_order_no__icontains=search) |
                Q(gvrma_no__icontains=search) |
                Q(engineer_name__icontains=search)
            )

        return queryset

    @action(detail=False, methods=['get'])
    def summary(self, request):
        queryset = self.get_queryset()
        total = queryset.count()
        regions = queryset.values('region').annotate(total=Count('id')).order_by('-total')
        return Response({
            'total': total,
            'regions': regions
        })

    def perform_create(self, serializer):
        user = self.request.user
        profile = getattr(user, 'userprofile', None)
        role = profile.role if profile else ''
        
        if role not in ['admin', 'super_admin', 'manager']:
            user_region = profile.region if profile else ''
            serializer.save(region=user_region)
        else:
            serializer.save()

    def perform_update(self, serializer):
        user = self.request.user
        profile = getattr(user, 'userprofile', None)
        role = profile.role if profile else ''
        
        if role not in ['admin', 'super_admin', 'manager']:
            user_region = profile.region if profile else ''
            serializer.save(region=user_region)
        else:
            serializer.save()
