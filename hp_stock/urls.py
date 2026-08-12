from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    HPStockItemViewSet, HPStockRMAPartViewSet, OpencallPartsCountViewSet,
    HPStockSettingsView,
)

router = DefaultRouter()
router.register(r'items', HPStockItemViewSet, basename='hpstockitem')
router.register(r'parts', HPStockRMAPartViewSet, basename='hpstockrmapart')
router.register(r'parts-call-counts', OpencallPartsCountViewSet, basename='opencallpartscount')

urlpatterns = [
    # Declared before the router so the singleton settings route is not shadowed
    # by a viewset lookup.
    path('settings/', HPStockSettingsView.as_view(), name='hp-stock-settings'),
    path('', include(router.urls)),
]
