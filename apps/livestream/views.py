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

from .filters import LiveEventFilter
from .serializers import (
    LiveEventDetailSerializer,
    LiveEventListSerializer,
    LiveEventWriteSerializer,
)
from .services import LiveEventService


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
        return LiveEventService.public_events()

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
            or user.role in [
                User.Role.EMPLOYEE,
                User.Role.ADMIN,
                User.Role.SUPER_ADMIN,
            ]
        ):
            return LiveEventService.all_events()

        return LiveEventService.public_events()