# urls.py
from django.urls import path
from .views import LoginAPIView

urlpatterns = [
    # ... your other urls ...
    path('login/', LoginAPIView.as_view(), name='api-login'),
]