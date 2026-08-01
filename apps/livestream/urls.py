from django.urls import path

from .views import (
    LiveEventDetailView,
    LiveEventListCreateView,
    LiveEventManagementListView,
    JoinLiveEventView,
)


urlpatterns = [
    path("<str:slug>/join/", JoinLiveEventView.as_view(), name="live-join"),
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
