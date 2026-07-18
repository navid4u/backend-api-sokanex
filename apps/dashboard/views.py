from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from common.responses import success_response
from rest_framework import serializers

from drf_spectacular.utils import (
    extend_schema,
    inline_serializer,
)
from .services import DashboardService
from .serializers import DashboardSerializer


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
    )
)
def get(self, request):
    def get(self, request):
        data = DashboardService.get_dashboard(
            request.user
        )

        serializer = DashboardSerializer(
            data,
            context={"request": request},
        )

        return success_response(
            data=serializer.data,
            message="Dashboard loaded successfully",
        )