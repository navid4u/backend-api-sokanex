from django.conf import settings
from django.core.cache import cache
from django.core import signing
from django.db import transaction
from django.db.models import F, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, serializers, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from common.permissions import CanManageInternalAnalysis, IsEmployee
from .models import Channel, ChannelPost
from .serializers import ChannelPostSerializer, InternalAnalysisPostSerializer
from common.serializers import EmptySerializer
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view


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


@extend_schema_view(get=extend_schema(parameters=[
    OpenApiParameter("scope", str, required=False, enum=["DOLLAR", "GOLD", "STOCK", "HOUSING"]),
    OpenApiParameter("page", int, required=False),
    OpenApiParameter("page_size", int, required=False),
]))
class InternalAnalysisChannelView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = InternalAnalysisPostSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ChannelPost.objects.none()
        queryset = ChannelPost.objects.filter(
            channel__slug="internal-analysis",
            channel__is_active=True,
            status=ChannelPost.Status.PUBLISHED,
            published_at__lte=timezone.now(),
        ).select_related("author").order_by("-is_pinned", "-published_at", "-created_at")
        scope = self.request.query_params.get("scope")
        if scope:
            queryset = queryset.filter(scope=scope)
        return queryset


@extend_schema_view(get=extend_schema(parameters=[
    OpenApiParameter("scope", str, required=False, enum=["DOLLAR", "GOLD", "STOCK", "HOUSING"]),
    OpenApiParameter("status", str, required=False, enum=["DRAFT", "SCHEDULED", "PUBLISHED"]),
    OpenApiParameter("search", str, required=False),
    OpenApiParameter("is_pinned", bool, required=False),
    OpenApiParameter("page", int, required=False),
    OpenApiParameter("page_size", int, required=False),
]))
class InternalAnalysisManageListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, CanManageInternalAnalysis]
    serializer_class = InternalAnalysisPostSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ChannelPost.objects.none()
        queryset = ChannelPost.objects.filter(
            channel__slug="internal-analysis"
        ).select_related("author").order_by("-is_pinned", "-published_at", "-created_at")
        if self.request.query_params.get("scope"):
            queryset = queryset.filter(scope=self.request.query_params["scope"])
        if self.request.query_params.get("status"):
            queryset = queryset.filter(status=self.request.query_params["status"])
        pinned = self.request.query_params.get("is_pinned")
        if pinned in ("true", "false"):
            queryset = queryset.filter(is_pinned=pinned == "true")
        search = self.request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) | Q(body__icontains=search)
                | Q(author__username__icontains=search)
                | Q(author__first_name__icontains=search)
                | Q(author__last_name__icontains=search)
            )
        return queryset

    def perform_create(self, serializer):
        channel = get_object_or_404(Channel, slug="internal-analysis", is_active=True)
        with transaction.atomic():
            serializer.save(channel=channel, author=self.request.user)


class InternalAnalysisManageDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, CanManageInternalAnalysis]
    serializer_class = InternalAnalysisPostSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        return ChannelPost.objects.filter(channel__slug="internal-analysis").select_related("author")

    def perform_update(self, serializer):
        with transaction.atomic():
            serializer.save()

    def perform_destroy(self, instance):
        with transaction.atomic():
            instance.delete()


class InternalAnalysisViewCountView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EmptySerializer

    def post(self, request, pk):
        post = get_object_or_404(
            ChannelPost,
            pk=pk,
            channel__slug="internal-analysis",
            status=ChannelPost.Status.PUBLISHED,
            published_at__lte=timezone.now(),
        )
        cache_key = f"internal-analysis:view:{request.user.pk}:{post.pk}"
        counted = cache.add(cache_key, True, timeout=30 * 60)
        if counted:
            ChannelPost.objects.filter(pk=post.pk).update(views_count=F("views_count") + 1)
        post.refresh_from_db(fields=["views_count"])
        return Response({"views_count": post.views_count, "counted": counted}, status=status.HTTP_200_OK)


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
