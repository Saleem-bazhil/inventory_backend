from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import HPStockItemViewSet, HPStockRMAPartViewSet, OpencallPartsCountViewSet

router = DefaultRouter()
router.register(r'items', HPStockItemViewSet, basename='hpstockitem')
router.register(r'parts', HPStockRMAPartViewSet, basename='hpstockrmapart')
router.register(r'parts-call-counts', OpencallPartsCountViewSet, basename='opencallpartscount')

urlpatterns = [
    path('', include(router.urls)),
]
