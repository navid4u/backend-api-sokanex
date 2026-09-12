from django.shortcuts import get_object_or_404

from django_filters.rest_framework import (
    DjangoFilterBackend,
)
from drf_spectacular.utils import (
    extend_schema,
    inline_serializer,
)
from rest_framework.permissions import IsAuthenticated

from rest_framework import (
    generics,
    serializers,
    status,
)
from rest_framework.filters import (
    OrderingFilter,
    SearchFilter,
)
from common.permissions import (
    IsEmployee,
    CanReviewSignals,
    IsSignalOwnerOrEmployee,
    IsTrader,
)
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.throttling import ScopedRateThrottle
from django.db import transaction
from django.db.models import Count
from apps.accounts.models import User



from .filters import SignalFilter
from .models import Signal, SignalUpdate
from .serializers import (
    SignalCreateSerializer,
    SignalDetailSerializer,
    SignalEditSerializer,
    SignalManagementSerializer,
    SignalListSerializer,
    SignalUpdateSerializer,
    SignalIngestionSerializer,
)
from .services import SignalService
from common.ingestion import FixedIngestionKeyAuthentication


class SignalPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data):
        summary = {"pending": 0, "approved": 0, "rejected": 0}
        summary.update({
            row["status"]: row["count"]
            for row in self.page.paginator.object_list.values("status").annotate(count=Count("id"))
        })
        response = super().get_paginated_response(data)
        response.data["summary"] = summary
        return response


class SignalListCreateView(
    generics.ListCreateAPIView
):

    filterset_class = SignalFilter
    pagination_class = SignalPagination

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
        if getattr(self, "swagger_fake_view", False):
            return Signal.objects.none()
        return SignalService.list_signals(
            self.request.user
        )

    def perform_create(self, serializer):
        SignalService.create_signal(
            self.request.user,
            serializer,
        )


class SignalIngestionView(APIView):
    authentication_classes = [FixedIngestionKeyAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "content_ingestion"

    @extend_schema(request=SignalIngestionSerializer, responses={200: SignalListSerializer, 201: SignalListSerializer})
    def post(self, request):
        serializer = SignalIngestionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        external_id = values.pop("external_id", None)
        defaults = {
            **values, "created_by": request.user, "approved_by": request.user,
            "source": Signal.Source.TELEGRAM_API, "status": "approved",
            "symbol": "", "market": "crypto", "direction": "buy",
            "entry_price": 0, "stop_loss": 0, "take_profit": 0,
            "allowed_level_1": True, "allowed_level_2": True,
            "allowed_level_3": True, "allowed_level_4": True,
            "allowed_level_5": True,
        }
        with transaction.atomic():
            if external_id:
                signal, created = Signal.objects.get_or_create(external_id=external_id, defaults=defaults)
            else:
                signal, created = Signal.objects.create(**defaults), True
        return Response(SignalListSerializer(signal, context={"request": request}).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class SignalDetailView(
    generics.RetrieveUpdateDestroyAPIView
):

    serializer_class = SignalDetailSerializer

    def get_permissions(self):
        permissions = [IsAuthenticated()]

        if self.request.method in [
            "PUT",
            "PATCH",
            "DELETE",
        ]:
            permissions.append(
                IsSignalOwnerOrEmployee()
            )

        return permissions

    def get_serializer_class(self):
        if self.request.method in [
            "PUT",
            "PATCH",
        ]:
            return SignalEditSerializer

        return SignalDetailSerializer

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

    def perform_update(self, serializer):
        previous_status = serializer.instance.status
        signal = serializer.save()
        if signal.status != previous_status and self.request.user.has_platform_permission(
            User.Permission.SIGNAL_REVIEW
        ):
            from django.utils import timezone
            from .models import SignalStatus
            signal.approved_by = self.request.user
            signal.closed_at = timezone.now() if signal.status in (
                SignalStatus.SUCCESSFUL, SignalStatus.FAILED, SignalStatus.CANCELLED,
            ) else None
            signal.save(update_fields=("approved_by", "closed_at", "updated_at"))
            SignalUpdate.objects.create(
                signal=signal, author=self.request.user, status=signal.status,
                title="Signal status updated",
                message=f"Status changed from {previous_status} to {signal.status}.",
            )


class SignalManagementListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, CanReviewSignals]
    serializer_class = SignalManagementSerializer
    pagination_class = SignalPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = SignalFilter
    search_fields = [
        "title", "symbol", "created_by__username", "created_by__first_name",
        "created_by__last_name",
    ]
    ordering_fields = ["created_at", "updated_at", "symbol", "status"]
    ordering = ["-created_at", "-id"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Signal.objects.none()
        return Signal.objects.select_related("created_by", "approved_by").all()
class PendingSignalListView(
    generics.ListAPIView
):

    permission_classes = [
        IsAuthenticated,
        CanReviewSignals,
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
        CanReviewSignals,
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
        CanReviewSignals,
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


class SignalUpdateListCreateView(generics.ListCreateAPIView):
    serializer_class = SignalUpdateSerializer
    permission_classes = [IsAuthenticated, IsSignalOwnerOrEmployee]

    def get_signal(self):
        return get_object_or_404(SignalService.accessible_signals(self.request.user), pk=self.kwargs["pk"])

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return SignalUpdate.objects.none()
        return SignalUpdate.objects.filter(signal=self.get_signal()).select_related("author")

    def perform_create(self, serializer):
        signal = self.get_signal()
        self.check_object_permissions(self.request, signal)
        update = serializer.save(signal=signal, author=self.request.user)
        if update.status:
            signal.status = update.status
            if update.status in ("successful", "failed", "cancelled"):
                from django.utils import timezone
                signal.closed_at = timezone.now()
            signal.save(update_fields=["status", "closed_at", "updated_at"])


class SignalUpdateDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = SignalUpdateSerializer
    permission_classes = [IsAuthenticated, IsSignalOwnerOrEmployee]
    lookup_url_kwarg = "update_id"

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return SignalUpdate.objects.none()
        return SignalUpdate.objects.filter(
            signal__in=SignalService.accessible_signals(self.request.user), signal_id=self.kwargs["pk"]
        ).select_related("signal", "author")

    def get_object(self):
        obj = super().get_object()
        self.check_object_permissions(self.request, obj.signal)
        return obj
