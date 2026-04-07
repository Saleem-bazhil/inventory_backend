from django.urls import path

from .views import (
    BufferListCreateView,
    BufferReleaseView,
    BufferUpdateView,
    LowStockView,
    PODetailView,
    POListCreateView,
    POReceiveView,
    POSendView,
    StockAdjustView,
    StockDetailView,
    StockListCreateView,
    StockMovementsView,
    StockReleaseView,
    StockReserveView,
    StockSearchView,
)

urlpatterns = [
    # Purchase Orders
    path('purchase-orders/', POListCreateView.as_view(), name='po-list'),
    path('purchase-orders/<int:pk>/', PODetailView.as_view(), name='po-detail'),
    path('purchase-orders/<int:pk>/send/', POSendView.as_view(), name='po-send'),
    path('purchase-orders/<int:pk>/receive/', POReceiveView.as_view(), name='po-receive'),

    # Stock
    path('stock/', StockListCreateView.as_view(), name='stock-list'),
    path('stock/low/', LowStockView.as_view(), name='stock-low'),
    path('stock/search/', StockSearchView.as_view(), name='stock-search'),
    path('stock/adjust/', StockAdjustView.as_view(), name='stock-adjust'),
    path('stock/<int:pk>/', StockDetailView.as_view(), name='stock-detail'),
    path('stock/<int:pk>/movements/', StockMovementsView.as_view(), name='stock-movements'),
    path('stock/<int:pk>/reserve/', StockReserveView.as_view(), name='stock-reserve'),
    path('stock/<int:pk>/release/', StockReleaseView.as_view(), name='stock-release'),

    # Buffer
    path('buffer/', BufferListCreateView.as_view(), name='buffer-list'),
    path('buffer/<int:pk>/', BufferUpdateView.as_view(), name='buffer-update'),
    path('buffer/<int:pk>/release/', BufferReleaseView.as_view(), name='buffer-release'),
]
