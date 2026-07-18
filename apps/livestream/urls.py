from django.urls import path

from .views import (
    LiveEventDetailView,
    LiveEventListCreateView,
    LiveEventManagementListView,
)


urlpatterns = [
    path(
        "manage/",
        LiveEventManagementListView.as_view(),
        name="live-management-list",
    ),

    path(
        "",
        LiveEventListCreateView.as_view(),
        name="live-list-create",
    ),

    path(
        "<str:slug>/",
        LiveEventDetailView.as_view(),
        name="live-detail",
    ),
]