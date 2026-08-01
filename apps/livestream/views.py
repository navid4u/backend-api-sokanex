from django_filters.rest_framework import (
    DjangoFilterBackend,
)

from rest_framework import generics
from rest_framework.filters import (
    OrderingFilter,
    SearchFilter,
)
from rest_framework.permissions import (
    IsAuthenticated,
)
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from django.shortcuts import get_object_or_404

from apps.accounts.models import User
from common.permissions import IsEmployee

from .filters import LiveEventFilter
from .serializers import (
    LiveEventDetailSerializer,
    LiveEventListSerializer,
    LiveEventWriteSerializer,
)
from .services import LiveEventService
from .models import LiveEvent
from apps.activity.models import UserActivity
from apps.activity.services import ActivityService


class LiveEventListCreateView(
    generics.ListCreateAPIView
):

    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]

    filterset_class = LiveEventFilter

    search_fields = [
        "title",
        "description",
        "host__username",
    ]

    ordering_fields = [
        "starts_at",
        "created_at",
        "title",
    ]

    def get_permissions(self):
        permissions = [
            IsAuthenticated(),
        ]

        if self.request.method == "POST":
            permissions.append(
                IsEmployee()
            )

        return permissions

    def get_serializer_class(self):
        if self.request.method == "POST":
            return LiveEventWriteSerializer

        return LiveEventListSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return LiveEvent.objects.none()
        return LiveEventService.public_events(
            self.request.user
        )

    def perform_create(self, serializer):
        serializer.save(
            created_by=self.request.user
        )


class LiveEventManagementListView(
    generics.ListAPIView
):

    permission_classes = [
        IsAuthenticated,
        IsEmployee,
    ]

    serializer_class = LiveEventListSerializer

    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]

    filterset_class = LiveEventFilter

    search_fields = [
        "title",
        "description",
        "host__username",
    ]

    ordering_fields = [
        "starts_at",
        "created_at",
        "updated_at",
        "title",
    ]

    def get_queryset(self):
        return LiveEventService.all_events()


class LiveEventDetailView(
    generics.RetrieveUpdateDestroyAPIView
):

    lookup_field = "slug"

    def get_permissions(self):
        permissions = [
            IsAuthenticated(),
        ]

        if self.request.method in [
            "PUT",
            "PATCH",
            "DELETE",
        ]:
            permissions.append(
                IsEmployee()
            )

        return permissions

    def get_serializer_class(self):
        if self.request.method in [
            "PUT",
            "PATCH",
        ]:
            return LiveEventWriteSerializer

        return LiveEventDetailSerializer

    def get_queryset(self):
        user = self.request.user

        if (
            user.is_superuser
            or user.has_platform_permission(
                User.Permission.CONTENT_MANAGE
            )
        ):
            return LiveEventService.all_events()

        return LiveEventService.public_events(user)


class JoinLiveEventView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None,
        responses=inline_serializer(
            name="JoinLiveEventResponse",
            fields={"join_url": serializers.URLField(), "provider": serializers.CharField()},
        ),
    )
    def post(self, request, slug):
        event = get_object_or_404(LiveEventService.public_events(request.user), slug=slug)
        join_url = event.provider_join_url or event.stream_url
        if not join_url:
            raise serializers.ValidationError("This live event does not have a join URL yet.")
        ActivityService.record(
            request.user, UserActivity.Type.LIVE_JOIN, "Live event joined",
            target_type="live_event", target_id=event.pk,
            target_url=f"/livestream/{event.slug}",
        )
        return Response({"join_url": join_url, "provider": event.provider})
