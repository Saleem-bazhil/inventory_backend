from django.urls import path

from .views import (
    CustomerResponseView,
    QuotationDetailView,
    QuotationListCreateView,
    SendQuotationView,
)

urlpatterns = [
    path('quotations/', QuotationListCreateView.as_view(), name='quotation-list'),
    path('quotations/<int:pk>/', QuotationDetailView.as_view(), name='quotation-detail'),
    path('quotations/<int:pk>/send/', SendQuotationView.as_view(), name='quotation-send'),
    path('quotations/<int:pk>/customer-response/', CustomerResponseView.as_view(), name='quotation-customer-response'),
]
