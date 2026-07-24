from django.urls import path

from .views import (
    ArticleDetailView,
    ArticleListCreateView,
    ArticleManagementListView,
    CategoryDetailView,
    CategoryListCreateView,
)


urlpatterns = [
    path(
        "categories/",
        CategoryListCreateView.as_view(),
        name="category-list-create",
    ),

    path(
        "manage/",
        ArticleManagementListView.as_view(),
        name="article-management-list",
    ),

    path(
        "",
        ArticleListCreateView.as_view(),
        name="article-list-create",
    ),

    path(
        "<str:slug>/",
        ArticleDetailView.as_view(),
        name="article-detail",
    ),
    path(
        "categories/<int:pk>/",
        CategoryDetailView.as_view(),
        name="category-detail",
    ),
]