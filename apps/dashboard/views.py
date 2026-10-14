from drf_spectacular.utils import (
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache

from common.responses import success_response

from .serializers import DashboardSerializer
from .services import DashboardService


@method_decorator(never_cache, name="dispatch")
class DashboardView(APIView):
    permission_classes = [
        IsAuthenticated,
    ]

    @extend_schema(
        responses=inline_serializer(
            name="DashboardResponse",
            fields={
                "success": serializers.BooleanField(),
                "message": serializers.CharField(),
                "data": DashboardSerializer(),
            },
        ),
    )
    def get(self, request):
        data = DashboardService.get_dashboard(
            request.user
        )

        serializer = DashboardSerializer(
            data,
            context={
                "request": request,
                "market_access_v2": data["market_access_v2"],
            },
        )

        return success_response(
            data=serializer.data,
            message="Dashboard loaded successfully",
        )
