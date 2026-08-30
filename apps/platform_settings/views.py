import hashlib

from django.core.cache import cache
from django.db import transaction
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from common.permissions import CanManagePlatform
from .models import PlatformSettings, SystemContent, UITranslationAuditLog, UITranslationCatalog
from .serializers import (
    FinancialSettingsSerializer, PublicPlatformSettingsSerializer,
    SystemContentSerializer,
    UITranslationCatalogSerializer, UITranslationReplaceSerializer,
)


PUBLIC_CACHE_KEY = "platform:settings:public:v1"
CONTENT_CACHE_KEY = "platform:content:v1"
TRANSLATION_CACHE_PREFIX = "platform:translations"


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


def _translation_cache_key(locale):
    return f"{TRANSLATION_CACHE_PREFIX}:{locale}:v1"


class AdminTranslationCatalogView(APIView):
    permission_classes = [CanManagePlatform]

    @extend_schema(responses={200: UITranslationCatalogSerializer})
    def get(self, request):
        return Response(UITranslationCatalogSerializer(UITranslationCatalog.load("en")).data)

    @extend_schema(request=UITranslationReplaceSerializer, responses={200: UITranslationCatalogSerializer})
    def patch(self, request):
        serializer = UITranslationReplaceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            UITranslationCatalog.load("en")
            catalog = UITranslationCatalog.objects.select_for_update().get(locale="en")
            previous_version = catalog.version
            catalog.translations = serializer.validated_data["translations"]
            catalog.version += 1
            catalog.updated_by = request.user
            catalog.save(update_fields=("translations", "version", "updated_by", "updated_at"))
            UITranslationAuditLog.objects.create(
                catalog=catalog, actor=request.user,
                previous_version=previous_version, new_version=catalog.version,
            )
        cache.delete(_translation_cache_key("en"))
        return Response(UITranslationCatalogSerializer(catalog).data)


class PublicTranslationCatalogView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses={200: UITranslationCatalogSerializer, 304: None})
    def get(self, request, locale):
        if locale != "en":
            from django.http import Http404
            raise Http404
        cache_key = _translation_cache_key(locale)
        data = cache.get(cache_key)
        if data is None:
            data = UITranslationCatalogSerializer(UITranslationCatalog.load(locale)).data
            cache.set(cache_key, data, 120)
        etag = '"' + hashlib.sha256(
            f"{locale}:{data['version']}:{data['updated_at']}".encode("utf-8")
        ).hexdigest() + '"'
        headers = {"ETag": etag, "Cache-Control": "public, max-age=120, must-revalidate"}
        if request.headers.get("If-None-Match") == etag:
            return Response(status=304, headers=headers)
        return Response(data, headers=headers)
