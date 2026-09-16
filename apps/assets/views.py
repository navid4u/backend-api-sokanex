from django.core.cache import cache
from django.db import transaction
from django.db.models import Prefetch, Q
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.pagination import DefaultPagination

from .models import AssetCatalogItem, AssetCategory, UserAssetHolding
from .serializers import (
    AssetCatalogItemSerializer,
    AssetCatalogResponseSerializer,
    UserAssetHoldingSerializer,
)
from .signals import CATALOG_CACHE_KEY


class AssetCatalogView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: AssetCatalogResponseSerializer})
    def get(self, request):
        search = request.query_params.get("search", "").strip()
        if not search:
            cached = cache.get(CATALOG_CACHE_KEY)
            if cached is not None:
                return Response(cached)

        items = AssetCatalogItem.objects.filter(is_active=True)
        categories = AssetCategory.objects.filter(is_active=True)
        if search:
            categories = categories.filter(
                Q(title_fa__icontains=search) | Q(assets__name_fa__icontains=search)
            ).distinct()
            items = items.filter(
                Q(name_fa__icontains=search) | Q(category__title_fa__icontains=search)
            )
        categories = categories.prefetch_related(
            Prefetch("assets", queryset=items.order_by("sort_order", "id"), to_attr="active_assets")
        ).order_by("sort_order", "id")
        results = []
        for category in categories:
            if search and not category.active_assets:
                continue
            assets = AssetCatalogItemSerializer(category.active_assets, many=True).data
            results.append({
                "code": category.code,
                "title": category.title_fa,
                "unit": assets[0]["unit"] if assets else None,
                "assets": assets,
            })
        payload = {"results": results}
        if not search:
            cache.set(CATALOG_CACHE_KEY, payload, timeout=300)
        return Response(payload)


class UserAssetHoldingListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserAssetHoldingSerializer
    pagination_class = DefaultPagination
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["asset__name_fa", "asset__category__title_fa", "note"]
    ordering_fields = ["updated_at", "created_at", "quantity"]
    ordering = ["-updated_at", "-id"]

    def get_queryset(self):
        queryset = UserAssetHolding.objects.filter(user=self.request.user).select_related(
            "asset", "asset__category"
        )
        category = self.request.query_params.get("category")
        if category:
            queryset = queryset.filter(asset__category__code=category)
        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        asset = values["asset"]
        defaults = {
            "quantity": values["quantity"],
            "unit": asset.unit,
            "note": values.get("note", ""),
        }
        with transaction.atomic():
            holding, created = UserAssetHolding.objects.update_or_create(
                user=request.user,
                asset=asset,
                defaults=defaults,
            )
        output = self.get_serializer(holding)
        return Response(
            output.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class UserAssetHoldingDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserAssetHoldingSerializer
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return UserAssetHolding.objects.filter(user=self.request.user).select_related(
            "asset", "asset__category"
        )
