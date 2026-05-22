from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from authenticate.views import EngineersListView

urlpatterns = [
    path('admin/', admin.site.urls),
    path("api-auth/", include("rest_framework.urls")),
    path('api/', include('material.urls')),
    path('api/', include('ticket.urls')),
    path('api/', include('customer.urls')),
    path('api/', include('parts.urls')),
    path('api/', include('quotation.urls')),
    path('api/', include('procurement.urls')),
    path('api/', include('buffer_stock.urls')),
    path('api/', include('invoice.urls')),
    path('api/hp-stock/', include('hp_stock.urls')),
    path('api/auth/', include('authenticate.urls')),
    path('api/users/engineers/', EngineersListView.as_view(), name='engineers-list'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

