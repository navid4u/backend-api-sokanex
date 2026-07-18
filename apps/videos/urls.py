from django.urls import path

from .views import (
    VideoCategoryListCreateView,
    VideoDetailView,
    VideoListCreateView,
    VideoManagementListView,
)


urlpatterns = [
    path(
        "categories/",
        VideoCategoryListCreateView.as_view(),
        name="video-category-list-create",
    ),

    path(
        "manage/",
        VideoManagementListView.as_view(),
        name="video-management-list",
    ),

    path(
        "",
        VideoListCreateView.as_view(),
        name="video-list-create",
    ),

    path(
        "<str:slug>/",
        VideoDetailView.as_view(),
        name="video-detail",
    ),
]