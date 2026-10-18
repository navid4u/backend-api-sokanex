"""Narrow read-only administrative views over existing user data."""

import logging

from django.shortcuts import get_object_or_404
from rest_framework import generics, serializers
from rest_framework.permissions import IsAuthenticated

from apps.assets.models import UserAssetHolding
from common.pagination import DefaultPagination
from common.permissions import IsSuperAdmin

from .models import User


logger = logging.getLogger(__name__)


class AdminAssetHoldingSerializer(serializers.ModelSerializer):
    asset_name = serializers.CharField(source="asset.name_fa", read_only=True)
    quantity = serializers.DecimalField(max_digits=28, decimal_places=8, read_only=True)
    unit = serializers.CharField(source="get_unit_display", read_only=True)

    class Meta:
        model = UserAssetHolding
        fields = ("id", "asset_name", "quantity", "unit")


class AdminUserAssetHoldingsView(generics.ListAPIView):
    """Superadmin-only projection; never changes ownership of a holding."""

    permission_classes = (IsAuthenticated, IsSuperAdmin)
    pagination_class = DefaultPagination
    serializer_class = AdminAssetHoldingSerializer

    def get_queryset(self):
        user_id = self.kwargs["user_id"]
        get_object_or_404(User, pk=user_id)
        logger.info(
            "admin_asset_holdings_read actor_id=%s subject_id=%s",
            self.request.user.pk, user_id,
        )
        return UserAssetHolding.objects.filter(user_id=user_id).select_related("asset").order_by("-updated_at", "-pk")
