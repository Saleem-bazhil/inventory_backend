from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import HPStockItemViewSet, HPStockRMAPartViewSet

router = DefaultRouter()
router.register(r'items', HPStockItemViewSet, basename='hpstockitem')
router.register(r'parts', HPStockRMAPartViewSet, basename='hpstockrmapart')

urlpatterns = [
    path('', include(router.urls)),
]
