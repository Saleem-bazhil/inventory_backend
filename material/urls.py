from django.urls import path,include
from .views import *
urlpatterns = [
    path('material-tracks/', MaterialTrackList.as_view(), name='material-track-list'),
    path('material-tracks/<int:pk>/', MaterialTrackDetail.as_view(), name='material-track-detail'),
]
