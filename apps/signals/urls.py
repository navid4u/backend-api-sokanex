from django.urls import path

from .views import (
    SignalListCreateView,
    SignalDetailView,
    PendingSignalListView,
    TraderSignalListView,
    ApproveSignalView,
    RejectSignalView,
)


urlpatterns = [
    path(
        "my-signals/",
        TraderSignalListView.as_view(),
        name="trader-signals",
    ),

    path(
        "pending/",
        PendingSignalListView.as_view(),
        name="pending-signals",
    ),

    path(
        "",
        SignalListCreateView.as_view(),
        name="signal-list-create",
    ),

    path(
        "<int:pk>/",
        SignalDetailView.as_view(),
        name="signal-detail",
    ),

    path(
        "<int:pk>/approve/",
        ApproveSignalView.as_view(),
        name="signal-approve",
    ),

    path(
        "<int:pk>/reject/",
        RejectSignalView.as_view(),
        name="signal-reject",
    ),
]