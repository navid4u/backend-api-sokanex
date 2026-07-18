from django.urls import path

from .views import (
    BrokerDetailView,
    BrokerListCreateView,
    BrokerManagementListView,
)


urlpatterns = [
    path(
        "manage/",
        BrokerManagementListView.as_view(),
        name="broker-management-list",
    ),

    path(
        "",
        BrokerListCreateView.as_view(),
        name="broker-list-create",
    ),

    path(
        "<str:slug>/",
        BrokerDetailView.as_view(),
        name="broker-detail",
    ),
]