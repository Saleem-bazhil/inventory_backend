from django.urls import path

from .views import (
    PartRequestApproveView,
    PartRequestDetailView,
    PartRequestListCreateView,
    PartRequestRejectView,
    PendingPartRequestsView,
)

urlpatterns = [
    path('part-requests/', PartRequestListCreateView.as_view(), name='part-request-list'),
    path('part-requests/pending/', PendingPartRequestsView.as_view(), name='part-request-pending'),
    path('part-requests/<int:pk>/', PartRequestDetailView.as_view(), name='part-request-detail'),
    path('part-requests/<int:pk>/approve/', PartRequestApproveView.as_view(), name='part-request-approve'),
    path('part-requests/<int:pk>/reject/', PartRequestRejectView.as_view(), name='part-request-reject'),
]
