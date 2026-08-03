from django_filters.rest_framework import (
    DjangoFilterBackend,
)

from rest_framework import generics, serializers, status
from rest_framework.filters import (
    OrderingFilter,
    SearchFilter,
)
from rest_framework.permissions import (
    IsAuthenticated,
)
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import timedelta
from django.core import signing
from django.conf import settings
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from common.serializers import EmptySerializer

from apps.accounts.models import User
from common.permissions import IsEmployee

from .filters import LiveEventFilter
from .serializers import (
    LiveEventDetailSerializer,
    LiveEventListSerializer,
    LiveEventWriteSerializer,
    LivePresenceSerializer,
    SpeakRequestSerializer,
    SpeakRequestReviewSerializer,
    LiveChatMessageSerializer,
)
from .services import LiveEventService
from .models import LiveChatMessage, LiveEvent, LivePresence, SpeakRequest


def host_can_manage(user, event):
    return user.is_staff or event.host_id == user.id or user.has_platform_permission(User.Permission.CONTENT_MANAGE)


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


class LivePresenceView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LivePresenceSerializer

    def get(self, request, slug):
        event = get_object_or_404(LiveEventService.public_events(request.user), slug=slug)
        LivePresence.objects.update_or_create(event=event, user=request.user, defaults={"left_at": None})
        active = LivePresence.objects.filter(event=event, left_at__isnull=True, last_seen_at__gte=timezone.now() - timedelta(minutes=2)).select_related("user")
        return Response({"viewer_count": active.count(), "results": LivePresenceSerializer(active, many=True).data})


class SpeakRequestCreateView(generics.CreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SpeakRequestSerializer

    def perform_create(self, serializer):
        event = get_object_or_404(LiveEventService.public_events(self.request.user), slug=self.kwargs["slug"], status=LiveEvent.Status.LIVE)
        if SpeakRequest.objects.filter(event=event, user=self.request.user, status=SpeakRequest.Status.PENDING).exists():
            raise serializers.ValidationError("You already have a pending speak request.")
        serializer.save(event=event, user=self.request.user)


class SpeakRequestReviewView(generics.UpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SpeakRequestReviewSerializer
    http_method_names = ["patch", "options"]
    lookup_url_kwarg = "request_id"

    def get_queryset(self):
        return SpeakRequest.objects.filter(event__slug=self.kwargs["slug"])

    def get_object(self):
        obj = super().get_object()
        if not host_can_manage(self.request.user, obj.event):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied()
        return obj

    def perform_update(self, serializer):
        serializer.save(reviewed_at=timezone.now())


class ParticipantMuteView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LivePresenceSerializer

    def post(self, request, slug, participant_id):
        event = get_object_or_404(LiveEvent, slug=slug)
        if not host_can_manage(request.user, event):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied()
        presence = get_object_or_404(LivePresence, event=event, pk=participant_id)
        presence.is_muted = bool(request.data.get("is_muted", True))
        presence.save(update_fields=["is_muted", "last_seen_at"])
        return Response(LivePresenceSerializer(presence).data)


class ParticipantRemoveView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LivePresenceSerializer

    def delete(self, request, slug, participant_id):
        event = get_object_or_404(LiveEvent, slug=slug)
        if not host_can_manage(request.user, event):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied()
        presence = get_object_or_404(LivePresence, event=event, pk=participant_id)
        presence.left_at = timezone.now()
        presence.save(update_fields=["left_at", "last_seen_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class LiveJoinView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EmptySerializer

    def post(self, request, slug):
        event = get_object_or_404(LiveEventService.public_events(request.user), slug=slug, status=LiveEvent.Status.LIVE)
        presence, _ = LivePresence.objects.update_or_create(event=event, user=request.user, defaults={"left_at": None})
        return Response({
            "event": event.slug,
            "join_url": event.provider_join_url or event.stream_url,
            "participant_id": presence.pk,
            "viewer_count": event.viewer_count,
        })


class LiveChatView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LiveChatMessageSerializer

    def get_event(self):
        return get_object_or_404(LiveEventService.public_events(self.request.user), slug=self.kwargs["slug"])

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return LiveChatMessage.objects.none()
        return LiveChatMessage.objects.filter(event=self.get_event()).select_related("sender")

    def perform_create(self, serializer):
        event = self.get_event()
        message = serializer.save(event=event, sender=self.request.user)
        async_to_sync(get_channel_layer().group_send)(
            f"livestream_{event.pk}",
            {"type": "live.event", "payload": {"type": "chat.created", "data": LiveChatMessageSerializer(message).data}},
        )


class LiveTicketView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EmptySerializer

    def post(self, request, slug):
        event = get_object_or_404(LiveEventService.public_events(request.user), slug=slug)
        ticket = signing.dumps({"user_id": request.user.pk, "event_id": event.pk}, salt="live-ws-ticket", compress=True)
        return Response({"ticket": ticket, "expires_in": settings.CHANNEL_TICKET_TTL_SECONDS})
