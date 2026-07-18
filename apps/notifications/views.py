from django.shortcuts import get_object_or_404

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

from common.permissions import IsEmployee

from .models import Notification
from .serializers import NotificationSerializer
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
        serializer.save(
            created_by=self.request.user
        )


class NotificationDetailView(
    generics.RetrieveAPIView
):

    permission_classes = [IsAuthenticated]

    serializer_class = NotificationSerializer

    def get_queryset(self):
        return (
            NotificationService
            .visible_notifications(
                self.request.user
            )
        )


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