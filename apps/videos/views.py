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

from apps.accounts.models import User
from common.permissions import IsEmployee

from .filters import VideoFilter
from .models import VideoCategory
from .serializers import (
    VideoCategorySerializer,
    VideoDetailSerializer,
    VideoListSerializer,
    VideoWriteSerializer,
)
from .services import VideoService
from apps.activity.models import UserActivity
from apps.activity.services import ActivityService


class VideoCategoryListCreateView(
    generics.ListCreateAPIView
):

    queryset = VideoCategory.objects.all()
    serializer_class = VideoCategorySerializer

    def get_permissions(self):
        permissions = [
            IsAuthenticated(),
        ]

        if self.request.method == "POST":
            permissions.append(
                IsEmployee()
            )

        return permissions


class VideoCategoryDetailView(
    generics.RetrieveUpdateDestroyAPIView
):

    queryset = VideoCategory.objects.all()
    serializer_class = VideoCategorySerializer

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


class VideoListCreateView(
    generics.ListCreateAPIView
):

    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]

    filterset_class = VideoFilter

    search_fields = [
        "title",
        "summary",
    ]

    ordering_fields = [
        "published_at",
        "created_at",
        "title",
        "duration_seconds",
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
            return VideoWriteSerializer

        return VideoListSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return VideoService.all_videos().none()
        return VideoService.published_videos(
            self.request.user
        )

    def perform_create(self, serializer):
        VideoService.create_video(
            serializer,
            self.request.user,
        )


class VideoManagementListView(
    generics.ListAPIView
):

    permission_classes = [
        IsAuthenticated,
        IsEmployee,
    ]

    serializer_class = VideoListSerializer

    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]

    filterset_class = VideoFilter

    search_fields = [
        "title",
        "summary",
    ]

    ordering_fields = [
        "published_at",
        "created_at",
        "updated_at",
        "title",
    ]

    def get_queryset(self):
        return VideoService.all_videos()


class VideoDetailView(
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
            return VideoWriteSerializer

        return VideoDetailSerializer

    def get_queryset(self):
        user = self.request.user

        if (
            user.is_superuser
            or user.has_platform_permission(
                User.Permission.CONTENT_MANAGE
            )
        ):
            return VideoService.all_videos()

        return VideoService.published_videos(user)

    def perform_update(self, serializer):
        VideoService.update_video(
            serializer
        )

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        video = self.get_object()
        ActivityService.record(
            request.user, UserActivity.Type.VIDEO_WATCH, "Video opened",
            target_type="video", target_id=video.pk,
            target_url=f"/videos/{video.slug}",
        )
        return response
