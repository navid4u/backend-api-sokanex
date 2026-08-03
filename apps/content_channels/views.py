from django.conf import settings
from django.core import signing
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from common.permissions import IsEmployee
from .models import Channel, ChannelPost
from .serializers import ChannelPostSerializer
from common.serializers import EmptySerializer
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def publish_channel_event(slug, event_type, data):
    async_to_sync(get_channel_layer().group_send)(
        f"content_channel_{slug.replace('-', '_')}",
        {"type": "channel.event", "payload": {"type": event_type, "data": data}},
    )


def accessible_channel(user, slug):
    queryset = Channel.objects.filter(slug=slug, is_active=True)
    if user.is_staff or user.role in (User.Role.EMPLOYEE, User.Role.ADMIN, User.Role.SUPER_ADMIN):
        return get_object_or_404(queryset)
    return get_object_or_404(queryset, min_access_level__lte=user.access_level)


class ChannelPostListCreateView(generics.ListCreateAPIView):
    serializer_class = ChannelPostSerializer
    permission_classes = [IsAuthenticated]
    channel_slug = None

    def get_permissions(self):
        permissions = [IsAuthenticated()]
        if self.request.method == "POST":
            permissions.append(IsEmployee())
        return permissions

    def get_channel(self):
        if not hasattr(self, "_channel"):
            self._channel = accessible_channel(self.request.user, self.channel_slug)
        return self._channel

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ChannelPost.objects.none()
        queryset = ChannelPost.objects.filter(channel=self.get_channel()).select_related("author", "signal")
        scope = self.request.query_params.get("scope")
        if scope:
            queryset = queryset.filter(scope=scope)
        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if not getattr(self, "swagger_fake_view", False):
            context["channel"] = self.get_channel()
        return context

    def perform_create(self, serializer):
        post = serializer.save(channel=self.get_channel(), author=self.request.user, published_at=serializer.validated_data.get("published_at", timezone.now()))
        publish_channel_event(post.channel.slug, "post.created", ChannelPostSerializer(post, context={"request": self.request}).data)


class VIPSignalChannelView(ChannelPostListCreateView):
    channel_slug = "vip-signals"


class InternalAnalysisChannelView(ChannelPostListCreateView):
    channel_slug = "internal-analysis"


class ChannelPostDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, IsEmployee]
    serializer_class = ChannelPostSerializer
    queryset = ChannelPost.objects.select_related("channel", "author", "signal")

    def perform_update(self, serializer):
        post = serializer.save()
        publish_channel_event(post.channel.slug, "post.updated", ChannelPostSerializer(post, context={"request": self.request}).data)

    def perform_destroy(self, instance):
        slug, post_id = instance.channel.slug, instance.pk
        instance.delete()
        publish_channel_event(slug, "post.deleted", {"id": post_id})


class ChannelTicketView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EmptySerializer

    def post(self, request):
        slug = request.data.get("channel")
        if slug not in ("vip-signals", "internal-analysis"):
            raise serializers.ValidationError({"channel": "Unknown channel."})
        accessible_channel(request.user, slug)
        ticket = signing.dumps({"user_id": request.user.pk, "channel": slug}, salt="channel-ws-ticket", compress=True)
        return Response({"ticket": ticket, "expires_in": settings.CHANNEL_TICKET_TTL_SECONDS})
