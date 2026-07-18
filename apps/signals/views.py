from django.shortcuts import get_object_or_404

from django_filters.rest_framework import (
    DjangoFilterBackend,
)
from drf_spectacular.utils import (
    extend_schema,
    inline_serializer,
)
from rest_framework import (
    generics,
    serializers,
    status,
)
from rest_framework.filters import (
    OrderingFilter,
    SearchFilter,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import (
    IsEmployee,
    IsTrader,
)

from .filters import SignalFilter
from .models import Signal
from .serializers import (
    SignalCreateSerializer,
    SignalDetailSerializer,
    SignalListSerializer,
)
from .services import SignalService


class SignalListCreateView(
    generics.ListCreateAPIView
):

    filterset_class = SignalFilter

    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]

    search_fields = [
        "title",
        "symbol",
    ]

    ordering_fields = [
        "created_at",
        "entry_price",
        "symbol",
    ]

    def get_permissions(self):
        if self.request.method == "POST":
            return [
                IsAuthenticated(),
                IsTrader(),
            ]

        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return SignalCreateSerializer

        return SignalListSerializer

    def get_queryset(self):
        return SignalService.list_signals()

    def perform_create(self, serializer):
        SignalService.create_signal(
            self.request.user,
            serializer,
        )


class SignalDetailView(
    generics.RetrieveAPIView
):

    permission_classes = [IsAuthenticated]

    serializer_class = SignalDetailSerializer

    def get_queryset(self):
        if getattr(
            self,
            "swagger_fake_view",
            False,
        ):
            return Signal.objects.none()

        return SignalService.accessible_signals(
            self.request.user
        )


class PendingSignalListView(
    generics.ListAPIView
):

    permission_classes = [
        IsAuthenticated,
        IsEmployee,
    ]

    serializer_class = SignalListSerializer

    def get_queryset(self):
        return SignalService.pending_signals()


class TraderSignalListView(
    generics.ListAPIView
):

    permission_classes = [
        IsAuthenticated,
        IsTrader,
    ]

    serializer_class = SignalListSerializer

    def get_queryset(self):
        if getattr(
            self,
            "swagger_fake_view",
            False,
        ):
            return Signal.objects.none()

        return SignalService.trader_signals(
            self.request.user
        )


class ApproveSignalView(APIView):

    permission_classes = [
        IsAuthenticated,
        IsEmployee,
    ]

    @extend_schema(
        request=None,
        responses=inline_serializer(
            name="ApproveSignalResponse",
            fields={
                "message": serializers.CharField(),
            },
        ),
    )
    def post(self, request, pk):
        signal = get_object_or_404(
            Signal,
            pk=pk,
        )

        SignalService.approve(
            signal,
            request.user,
        )

        return Response(
            {
                "message": "Signal approved.",
            },
            status=status.HTTP_200_OK,
        )


class RejectSignalView(APIView):

    permission_classes = [
        IsAuthenticated,
        IsEmployee,
    ]

    @extend_schema(
        request=inline_serializer(
            name="RejectSignalRequest",
            fields={
                "reason": serializers.CharField(
                    required=False,
                    allow_blank=True,
                ),
            },
        ),
        responses=inline_serializer(
            name="RejectSignalResponse",
            fields={
                "message": serializers.CharField(),
            },
        ),
    )
    def post(self, request, pk):
        signal = get_object_or_404(
            Signal,
            pk=pk,
        )

        SignalService.reject(
            signal,
            request.user,
            request.data.get("reason", ""),
        )

        return Response(
            {
                "message": "Signal rejected.",
            },
            status=status.HTTP_200_OK,
        )