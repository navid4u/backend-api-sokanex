from django.shortcuts import get_object_or_404

from drf_spectacular.utils import (
    extend_schema,
    inline_serializer,
)
from rest_framework import (
    generics,
    mixins,
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

from common.permissions import IsEmployee

from .models import Notification, WebPushSubscription
from .serializers import (
    NotificationSerializer,
    WebPushSubscriptionCreateSerializer,
    WebPushSubscriptionSerializer,
)
from .services import NotificationService


class NotificationListCreateView(
    generics.ListCreateAPIView
):

    serializer_class = NotificationSerializer

    filter_backends = [
        SearchFilter,
        OrderingFilter,
    ]

    search_fields = [
        "title",
        "message",
    ]

    ordering_fields = [
        "created_at",
        "notification_type",
    ]

    def get_permissions(self):
        permissions = [IsAuthenticated()]

        if self.request.method == "POST":
            permissions.append(IsEmployee())

        return permissions

    def get_queryset(self):
        queryset = (
            NotificationService
            .visible_notifications(
                self.request.user
            )
        )

        is_read = self.request.query_params.get(
            "is_read"
        )

        if is_read == "true":
            queryset = queryset.filter(
                is_read=True
            )

        elif is_read == "false":
            queryset = queryset.filter(
                is_read=False
            )

        return queryset

    def perform_create(self, serializer):
        notification = serializer.save(
            created_by=self.request.user
        )
        NotificationService.queue_sms(notification)
        NotificationService.queue_push(notification)


class NotificationUnreadCountView(APIView):

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses=inline_serializer(
            name="NotificationUnreadCountResponse",
            fields={
                "unread_count": (
                    serializers.IntegerField()
                ),
            },
        ),
    )
    def get(self, request):
        count = NotificationService.unread_count(
            request.user
        )

        return Response(
            {
                "unread_count": count,
            },
            status=status.HTTP_200_OK,
        )


class WebPushVapidPublicKeyView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=inline_serializer(
        name="WebPushVapidPublicKeyResponse",
        fields={"configured": serializers.BooleanField(), "public_key": serializers.CharField(allow_null=True)},
    ))
    def get(self, request):
        from django.conf import settings
        from pathlib import Path

        configured = bool(
            settings.WEBPUSH_VAPID_PUBLIC_KEY
            and settings.WEBPUSH_VAPID_PRIVATE_KEY_PATH
            and settings.WEBPUSH_VAPID_SUBJECT
            and Path(settings.WEBPUSH_VAPID_PRIVATE_KEY_PATH).is_file()
        )
        return Response({
            "configured": configured,
            "public_key": settings.WEBPUSH_VAPID_PUBLIC_KEY if configured else None,
        })


class WebPushSubscriptionListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=WebPushSubscriptionSerializer(many=True))
    def get(self, request):
        subscriptions = WebPushSubscription.objects.filter(user=request.user)
        return Response(WebPushSubscriptionSerializer(subscriptions, many=True).data)

    @extend_schema(request=WebPushSubscriptionCreateSerializer, responses={200: WebPushSubscriptionSerializer, 201: WebPushSubscriptionSerializer})
    def post(self, request):
        serializer = WebPushSubscriptionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        subscription = WebPushSubscription.objects.filter(endpoint=data["endpoint"]).first()
        if subscription and subscription.user_id != request.user.pk:
            return Response(
                {"detail": "This push endpoint is already linked to another account."},
                status=status.HTTP_409_CONFLICT,
            )
        created = subscription is None
        subscription = subscription or WebPushSubscription(user=request.user, endpoint=data["endpoint"])
        subscription.user = request.user
        subscription.p256dh = data["keys"]["p256dh"]
        subscription.auth = data["keys"]["auth"]
        subscription.user_agent = request.META.get("HTTP_USER_AGENT", "")[:500]
        subscription.is_active = True
        subscription.save()
        return Response(
            WebPushSubscriptionSerializer(subscription).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class WebPushSubscriptionDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={204: None})
    def delete(self, request, pk):
        subscription = get_object_or_404(WebPushSubscription, pk=pk, user=request.user)
        subscription.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class NotificationDetailView(
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    generics.GenericAPIView,
):
    serializer_class = NotificationSerializer

    def get_permissions(self):
        permissions = [IsAuthenticated()]
        if self.request.method in ("PATCH", "DELETE"):
            permissions.append(IsEmployee())
        return permissions

    def get_queryset(self):
        if self.request.method in ("PATCH", "DELETE"):
            return Notification.objects.select_related(
                "created_by",
                "recipient",
            )
        return (
            NotificationService
            .visible_notifications(
                self.request.user
            )
        )

    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)

    def patch(self, request, *args, **kwargs):
        return self.partial_update(
            request,
            *args,
            **kwargs,
        )

    def delete(self, request, *args, **kwargs):
        return self.destroy(request, *args, **kwargs)


class MarkNotificationReadView(APIView):

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None,
        responses=inline_serializer(
            name="MarkNotificationReadResponse",
            fields={
                "message": serializers.CharField(),
            },
        ),
    )
    def post(self, request, pk):
        notification = get_object_or_404(
            NotificationService
            .visible_notifications(
                request.user
            ),
            pk=pk,
        )

        NotificationService.mark_as_read(
            notification,
            request.user,
        )

        return Response(
            {
                "message": (
                    "Notification marked as read."
                ),
            },
            status=status.HTTP_200_OK,
        )


class MarkAllNotificationsReadView(APIView):

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None,
        responses=inline_serializer(
            name=(
                "MarkAllNotificationsReadResponse"
            ),
            fields={
                "message": serializers.CharField(),
                "marked_count": (
                    serializers.IntegerField()
                ),
            },
        ),
    )
    def post(self, request):
        count = (
            NotificationService
            .mark_all_as_read(
                request.user
            )
        )

        return Response(
            {
                "message": (
                    "All notifications marked as read."
                ),
                "marked_count": count,
            },
            status=status.HTTP_200_OK,
        )
