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

from .filters import ArticleFilter
from .models import Category
from .serializers import (
    ArticleDetailSerializer,
    ArticleListSerializer,
    ArticleWriteSerializer,
    CategorySerializer,
)
from .services import ArticleService


class CategoryListCreateView(
    generics.ListCreateAPIView
):

    queryset = Category.objects.all()
    serializer_class = CategorySerializer

    def get_permissions(self):
        permissions = [
            IsAuthenticated(),
        ]

        if self.request.method == "POST":
            permissions.append(
                IsEmployee()
            )

        return permissions


class ArticleListCreateView(
    generics.ListCreateAPIView
):

    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]

    filterset_class = ArticleFilter

    search_fields = [
        "title",
        "summary",
        "content",
    ]

    ordering_fields = [
        "published_at",
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
            return ArticleWriteSerializer

        return ArticleListSerializer

    def get_queryset(self):
        return ArticleService.published_articles()

    def perform_create(self, serializer):
        ArticleService.create_article(
            serializer,
            self.request.user,
        )


class ArticleManagementListView(
    generics.ListAPIView
):

    permission_classes = [
        IsAuthenticated,
        IsEmployee,
    ]

    serializer_class = ArticleListSerializer

    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]

    filterset_class = ArticleFilter

    search_fields = [
        "title",
        "summary",
        "content",
    ]

    ordering_fields = [
        "published_at",
        "created_at",
        "updated_at",
        "title",
    ]

    def get_queryset(self):
        return ArticleService.all_articles()


class ArticleDetailView(
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
            return ArticleWriteSerializer

        return ArticleDetailSerializer

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
            return ArticleService.all_articles()

        return ArticleService.published_articles()

    def perform_update(self, serializer):
        ArticleService.update_article(
            serializer
        )