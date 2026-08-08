from django_filters.rest_framework import (
    DjangoFilterBackend,
)

from rest_framework import generics, serializers, status
from rest_framework.filters import (
    OrderingFilter,
    SearchFilter,
)
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import timedelta
from django.core import signing
from django.conf import settings
from django.db import transaction
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from common.serializers import EmptySerializer

from apps.accounts.models import User
from common.permissions import CanManageLive

from .filters import LiveEventFilter
from .serializers import (
    LiveEventDetailSerializer,
    LiveEventListSerializer,
    LiveEventWriteSerializer,
    LiveEventManagementSerializer,
    LivePresenceSerializer,
    SpeakRequestSerializer,
    SpeakRequestReviewSerializer,
    LiveChatMessageSerializer,
    LiveRecordingSerializer,
)
from .services import LiveEventService
from .models import LiveChatMessage, LiveEvent, LivePresence, LiveRecording, SpeakRequest
from .livekit import (
    create_participant_token, receive_webhook, remove_participant,
    start_recording, stop_recording, update_participant_permissions,
)


def host_can_manage(user, event):
    return event.host_id == user.id or user.has_platform_permission(User.Permission.LIVE_MANAGE)


def broadcast_live_event(event, event_type, data):
    async_to_sync(get_channel_layer().group_send)(
        f"livestream_{event.pk}",
        {"type": "live.event", "payload": {"type": event_type, "data": data}},
    )


class LiveCapacityFull(APIException):
    status_code = 409
    default_code = "LIVE_CAPACITY_FULL"
    default_detail = "This live event has reached its participant limit."


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
                CanManageLive()
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
        CanManageLive,
    ]

    serializer_class = LiveEventManagementSerializer

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
                CanManageLive()
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
                User.Permission.LIVE_MANAGE
            )
        ):
            return LiveEventService.all_events()

        return LiveEventService.public_events(user)


class LivePresenceView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LivePresenceSerializer

    def get(self, request, slug):
        event = get_object_or_404(LiveEventService.public_events(request.user), slug=slug)
        active = LivePresence.objects.filter(event=event, left_at__isnull=True, last_seen_at__gte=timezone.now() - timedelta(minutes=2)).select_related("user")
        data = {
            "actual_viewer_count": active.count(),
            "display_viewer_count": active.count() + event.viewer_display_offset,
            "max_participants": event.max_participants,
        }
        data["results"] = LivePresenceSerializer(active, many=True).data if host_can_manage(request.user, event) else []
        return Response(data)

    def post(self, request, slug):
        event = get_object_or_404(LiveEventService.public_events(request.user), slug=slug, status=LiveEvent.Status.LIVE)
        presence = get_object_or_404(LivePresence, event=event, user=request.user, left_at__isnull=True)
        presence.save(update_fields=["last_seen_at"])
        return Response({"last_seen_at": presence.last_seen_at})

    def delete(self, request, slug):
        event = get_object_or_404(LiveEvent, slug=slug)
        LivePresence.objects.filter(event=event, user=request.user, left_at__isnull=True).update(left_at=timezone.now())
        return Response(status=status.HTTP_204_NO_CONTENT)


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
        speak_request = serializer.save(reviewed_at=timezone.now())
        LivePresence.objects.filter(event=speak_request.event, user=speak_request.user).update(
            can_publish=speak_request.status == SpeakRequest.Status.APPROVED,
            is_muted=speak_request.status != SpeakRequest.Status.APPROVED,
        )


class ParticipantMuteView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LivePresenceSerializer

    def post(self, request, slug, participant_id):
        event = get_object_or_404(LiveEvent, slug=slug)
        if not host_can_manage(request.user, event):
            raise PermissionDenied()
        presence = get_object_or_404(LivePresence, event=event, pk=participant_id)
        presence.is_muted = bool(request.data.get("is_muted", True))
        presence.can_publish = not presence.is_muted
        presence.save(update_fields=["is_muted", "can_publish", "last_seen_at"])
        if settings.LIVEKIT_API_KEY:
            update_participant_permissions(event, presence.user, presence.can_publish)
        return Response(LivePresenceSerializer(presence).data)


class ParticipantRemoveView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LivePresenceSerializer

    def delete(self, request, slug, participant_id):
        event = get_object_or_404(LiveEvent, slug=slug)
        if not host_can_manage(request.user, event):
            raise PermissionDenied()
        presence = get_object_or_404(LivePresence, event=event, pk=participant_id)
        presence.left_at = timezone.now()
        presence.removed_by = request.user
        presence.save(update_fields=["left_at", "removed_by", "last_seen_at"])
        if settings.LIVEKIT_API_KEY:
            remove_participant(event, presence.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class LiveJoinView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EmptySerializer

    def post(self, request, slug):
        with transaction.atomic():
            event = get_object_or_404(
                LiveEvent.objects.select_for_update(), pk__in=LiveEventService.public_events(request.user),
                slug=slug, status=LiveEvent.Status.LIVE,
            )
            if not event.room_name:
                event.save()
            active = LivePresence.objects.filter(
                event=event, left_at__isnull=True,
                last_seen_at__gte=timezone.now() - timedelta(minutes=2),
            )
            existing = active.filter(user=request.user).first()
            if not existing and active.count() >= event.max_participants and not host_can_manage(request.user, event):
                raise LiveCapacityFull()
            can_publish = host_can_manage(request.user, event) or SpeakRequest.objects.filter(
                event=event, user=request.user, status=SpeakRequest.Status.APPROVED,
            ).exists()
            presence, _ = LivePresence.objects.update_or_create(
                event=event, user=request.user,
                defaults={"left_at": None, "is_muted": not can_publish, "can_publish": can_publish, "removed_by": None},
            )
        token = create_participant_token(
            event, request.user, can_publish=can_publish, room_admin=host_can_manage(request.user, event),
        )
        return Response({
            "event": event.slug,
            "join_url": event.provider_join_url or event.stream_url,
            "livekit_url": settings.LIVEKIT_URL,
            "participant_token": token,
            "room_name": event.room_name,
            "can_publish": can_publish,
            "participant_id": presence.pk,
            "actual_viewer_count": event.viewer_count,
            "display_viewer_count": event.display_viewer_count,
            "max_participants": event.max_participants,
            "comments_enabled": event.comments_enabled,
        })


class LiveChatView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LiveChatMessageSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "live_chat"

    def get_event(self):
        return get_object_or_404(LiveEventService.public_events(self.request.user), slug=self.kwargs["slug"])

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return LiveChatMessage.objects.none()
        return LiveChatMessage.objects.filter(event=self.get_event(), is_deleted=False).select_related("sender")

    def perform_create(self, serializer):
        event = self.get_event()
        if event.status != LiveEvent.Status.LIVE:
            raise serializers.ValidationError({"event": "Comments are only available while the event is live."})
        if not event.comments_enabled:
            raise PermissionDenied("Comments are disabled for this event.")
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


class LiveEventStartView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EmptySerializer

    def post(self, request, slug):
        event = get_object_or_404(LiveEvent, slug=slug)
        if not host_can_manage(request.user, event):
            raise PermissionDenied()
        if event.status not in (LiveEvent.Status.SCHEDULED, LiveEvent.Status.LIVE):
            raise serializers.ValidationError({"status": "Only a scheduled event can be started."})
        event.status = LiveEvent.Status.LIVE
        event.is_active = True
        event.ended_at = None
        if not event.room_name:
            event.save()
        else:
            event.save(update_fields=("status", "is_active", "ended_at", "updated_at"))
        broadcast_live_event(event, "live.started", {"slug": event.slug, "started_at": timezone.now().isoformat()})
        return Response(LiveEventDetailSerializer(event, context={"request": request}).data)


class LiveEventEndView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EmptySerializer

    def post(self, request, slug):
        event = get_object_or_404(LiveEvent, slug=slug)
        if not host_can_manage(request.user, event):
            raise PermissionDenied()
        event.status = LiveEvent.Status.ENDED
        event.ended_at = timezone.now()
        event.ends_at = event.ends_at or event.ended_at
        event.save(update_fields=("status", "ended_at", "ends_at", "updated_at"))
        LivePresence.objects.filter(event=event, left_at__isnull=True).update(left_at=event.ended_at)
        for recording in event.recordings.filter(status__in=(LiveRecording.Status.STARTING, LiveRecording.Status.ACTIVE)):
            try:
                stop_recording(recording.egress_id)
                recording.status = LiveRecording.Status.ENDING
                recording.save(update_fields=("status", "updated_at"))
            except APIException as exc:
                recording.error = str(exc.detail)[:1000]
                recording.save(update_fields=("error", "updated_at"))
        broadcast_live_event(event, "live.ended", {"slug": event.slug, "ended_at": event.ended_at.isoformat()})
        return Response(LiveEventDetailSerializer(event, context={"request": request}).data)


class LiveRecordingListStartView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LiveRecordingSerializer

    def get_event(self, request, slug):
        event = get_object_or_404(LiveEvent, slug=slug)
        if not host_can_manage(request.user, event):
            raise PermissionDenied()
        return event

    def get(self, request, slug):
        event = self.get_event(request, slug)
        return Response({"results": LiveRecordingSerializer(event.recordings.all(), many=True).data})

    def post(self, request, slug):
        event = self.get_event(request, slug)
        if event.status != LiveEvent.Status.LIVE:
            raise serializers.ValidationError({"status": "Recording can only start during a live event."})
        if event.recordings.filter(status__in=(LiveRecording.Status.STARTING, LiveRecording.Status.ACTIVE)).exists():
            raise serializers.ValidationError({"recording": "A recording is already active."})
        if not event.room_name:
            event.save()
        result, file_path = start_recording(event)
        recording = LiveRecording.objects.create(
            event=event, egress_id=result.egress_id, status=LiveRecording.Status.STARTING,
            file_path=file_path, started_by=request.user,
        )
        broadcast_live_event(event, "recording.started", LiveRecordingSerializer(recording).data)
        return Response(LiveRecordingSerializer(recording).data, status=status.HTTP_201_CREATED)


class LiveRecordingStopView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LiveRecordingSerializer

    def post(self, request, slug, recording_id):
        event = get_object_or_404(LiveEvent, slug=slug)
        if not host_can_manage(request.user, event):
            raise PermissionDenied()
        recording = get_object_or_404(event.recordings, pk=recording_id)
        if recording.status not in (LiveRecording.Status.STARTING, LiveRecording.Status.ACTIVE):
            raise serializers.ValidationError({"recording": "Recording is not active."})
        stop_recording(recording.egress_id)
        recording.status = LiveRecording.Status.ENDING
        recording.save(update_fields=("status", "updated_at"))
        return Response(LiveRecordingSerializer(recording).data)


class LiveChatMessageDeleteView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LiveChatMessageSerializer

    def delete(self, request, slug, message_id):
        event = get_object_or_404(LiveEvent, slug=slug)
        if not host_can_manage(request.user, event):
            raise PermissionDenied()
        message = get_object_or_404(LiveChatMessage, event=event, pk=message_id)
        message.is_deleted = True
        message.deleted_at = timezone.now()
        message.deleted_by = request.user
        message.save(update_fields=("is_deleted", "deleted_at", "deleted_by"))
        broadcast_live_event(event, "chat.deleted", {"id": message.pk})
        return Response(status=status.HTTP_204_NO_CONTENT)


class LiveKitWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = EmptySerializer

    def post(self, request):
        event_data = receive_webhook(
            request.body.decode("utf-8"), request.headers.get("Authorization", ""),
        )
        room_name = getattr(getattr(event_data, "room", None), "name", "")
        event = LiveEvent.objects.filter(room_name=room_name).first()
        if not event:
            return Response({"received": True})
        identity = getattr(getattr(event_data, "participant", None), "identity", "")
        if identity.startswith("user-") and identity[5:].isdigit():
            presence = LivePresence.objects.filter(event=event, user_id=int(identity[5:])).first()
            if presence and event_data.event == "participant_left":
                presence.left_at = timezone.now()
                presence.save(update_fields=("left_at", "last_seen_at"))
        egress = getattr(event_data, "egress_info", None)
        if egress and egress.egress_id:
            recording = LiveRecording.objects.filter(event=event, egress_id=egress.egress_id).first()
            if recording:
                if event_data.event in ("egress_started", "egress_updated"):
                    recording.status = LiveRecording.Status.ACTIVE
                elif event_data.event == "egress_ended":
                    recording.status = LiveRecording.Status.FAILED if egress.error else LiveRecording.Status.COMPLETE
                    recording.ended_at = timezone.now()
                    recording.error = egress.error[:1000]
                    base_url = settings.LIVEKIT_RECORDING_PUBLIC_BASE_URL.rstrip("/")
                    if base_url and recording.file_path:
                        recording.playback_url = f"{base_url}/{recording.file_path.lstrip('/')}"
                        event.replay_url = recording.playback_url
                        event.save(update_fields=("replay_url", "updated_at"))
                recording.save()
        return Response({"received": True})
