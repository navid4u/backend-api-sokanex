from django.core.cache import cache
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import CanManagePlatform
from .models import PlatformSettings, SystemContent
from .serializers import (
    FinancialSettingsSerializer, PublicPlatformSettingsSerializer,
    SystemContentSerializer,
)


PUBLIC_CACHE_KEY = "platform:settings:public:v1"
CONTENT_CACHE_KEY = "platform:content:v1"


class PublicSettingsView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = PublicPlatformSettingsSerializer

    def get(self, request):
        data = cache.get(PUBLIC_CACHE_KEY)
        if data is None:
            data = PublicPlatformSettingsSerializer(PlatformSettings.load()).data
            cache.set(PUBLIC_CACHE_KEY, data, 300)
        return Response(data)


class FinancialSettingsView(generics.RetrieveUpdateAPIView):
    permission_classes = [CanManagePlatform]
    serializer_class = FinancialSettingsSerializer

    def get_object(self):
        return PlatformSettings.load()

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)
        cache.delete(PUBLIC_CACHE_KEY)


class SystemContentListView(generics.ListAPIView):
    permission_classes = [CanManagePlatform]
    serializer_class = SystemContentSerializer
    pagination_class = None

    def get_queryset(self):
        return SystemContent.objects.all()

    def list(self, request, *args, **kwargs):
        data = cache.get(CONTENT_CACHE_KEY)
        if data is None:
            data = self.get_serializer(self.get_queryset(), many=True).data
            cache.set(CONTENT_CACHE_KEY, data, 300)
        return Response(data)


class SystemContentUpdateView(generics.UpdateAPIView):
    permission_classes = [CanManagePlatform]
    serializer_class = SystemContentSerializer
    queryset = SystemContent.objects.all()
    lookup_field = "key"

    def perform_update(self, serializer):
        serializer.save()
        cache.delete(CONTENT_CACHE_KEY)
