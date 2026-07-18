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

from .filters import BrokerFilter
from .serializers import (
    BrokerDetailSerializer,
    BrokerListSerializer,
    BrokerWriteSerializer,
)
from .services import BrokerService


class BrokerListCreateView(
    generics.ListCreateAPIView
):

    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]

    filterset_class = BrokerFilter

    search_fields = [
        "name",
        "short_description",
        "description",
        "country",
        "regulation",
    ]

    ordering_fields = [
        "name",
        "rating",
        "minimum_deposit",
        "sort_order",
        "created_at",
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
            return BrokerWriteSerializer

        return BrokerListSerializer

    def get_queryset(self):
        return BrokerService.active_brokers()


class BrokerManagementListView(
    generics.ListAPIView
):

    permission_classes = [
        IsAuthenticated,
        IsEmployee,
    ]

    serializer_class = BrokerListSerializer

    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]

    filterset_class = BrokerFilter

    search_fields = [
        "name",
        "description",
        "country",
        "regulation",
    ]

    ordering_fields = [
        "name",
        "rating",
        "sort_order",
        "created_at",
    ]

    def get_queryset(self):
        return BrokerService.all_brokers()


class BrokerDetailView(
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
            return BrokerWriteSerializer

        return BrokerDetailSerializer

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
            return BrokerService.all_brokers()

        return BrokerService.active_brokers()