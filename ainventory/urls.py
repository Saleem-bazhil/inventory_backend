from django.contrib import admin
from django.urls import path, include

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
    path('api/', include('invoice.urls')),
    path('api/auth/', include('authenticate.urls')),
    path('api/users/engineers/', EngineersListView.as_view(), name='engineers-list'),
]
