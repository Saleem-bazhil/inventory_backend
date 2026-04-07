from django.urls import path

from .views import (
    InvoiceDetailView,
    InvoiceListCreateView,
    MarkPaidView,
    SendInvoiceView,
)

urlpatterns = [
    path('invoices/', InvoiceListCreateView.as_view(), name='invoice-list'),
    path('invoices/<int:pk>/', InvoiceDetailView.as_view(), name='invoice-detail'),
    path('invoices/<int:pk>/send/', SendInvoiceView.as_view(), name='invoice-send'),
    path('invoices/<int:pk>/mark-paid/', MarkPaidView.as_view(), name='invoice-mark-paid'),
]
