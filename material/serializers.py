from rest_framework import serializers
from .models import *
class MaterialSerializer(serializers.ModelSerializer):
    class Meta:
        model = MaterialTrack
        fields = '__all__'  