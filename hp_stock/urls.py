from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import HPStockItemViewSet

router = DefaultRouter()
router.register(r'items', HPStockItemViewSet, basename='hpstockitem')

urlpatterns = [
    path('', include(router.urls)),
]
