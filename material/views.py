from django.shortcuts import render
from .models import *
from .serializers import *
from rest_framework import generics
# Create your views here.
class MaterialTrackList(generics.ListCreateAPIView):
    queryset = MaterialTrack.objects.all()
    serializer_class = MaterialSerializer

class MaterialTrackDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = MaterialTrack.objects.all()
    serializer_class = MaterialSerializer