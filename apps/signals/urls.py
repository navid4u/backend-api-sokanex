from django.urls import path

from .views import (
    SignalListCreateView,
    SignalDetailView,
    PendingSignalListView,
    TraderSignalListView,
    ApproveSignalView,
    RejectSignalView,
    SignalUpdateListCreateView,
    SignalUpdateDetailView,
    SignalManagementListView,
    SignalIngestionView,
    ManualSignalPostListCreateView,
    ManualSignalPostDeleteView,
    VIPSignalPostDetailView,
    VIPSignalPostIngestionView,
    VIPSignalPostListView,
    VIPSignalPostManagementDetailView,
    VIPSignalPostManagementListView,
)


urlpatterns = [
    path("", VIPSignalPostListView.as_view(), name="vip-signal-post-list"),
    path("channels/crypto/ingest/", VIPSignalPostIngestionView.as_view(), {"channel": "crypto"}, name="vip-signal-crypto-ingest"),
    path("channels/forex/ingest/", VIPSignalPostIngestionView.as_view(), {"channel": "forex"}, name="vip-signal-forex-ingest"),
    path("manage/", VIPSignalPostManagementListView.as_view(), name="vip-signal-management-list"),
    path("manage/<int:pk>/", VIPSignalPostManagementDetailView.as_view(), name="vip-signal-management-detail"),
    path("<int:pk>/", VIPSignalPostDetailView.as_view(), name="vip-signal-post-detail"),

    # The previous trading-signal implementation is retained for rollback/data access,
    # but it is intentionally removed from the active customer and management feeds.
    path("legacy/manual-posts/", ManualSignalPostListCreateView.as_view(), name="manual-signal-post-list-create"),
    path("legacy/manual-posts/<int:pk>/", ManualSignalPostDeleteView.as_view(), name="manual-signal-post-delete"),
    path("legacy/ingest/", SignalIngestionView.as_view(), name="signal-ingest"),
    path("legacy/manage/", SignalManagementListView.as_view(), name="signal-management-list"),
    path("legacy/<int:pk>/updates/", SignalUpdateListCreateView.as_view(), name="signal-update-list-create"),
    path("legacy/<int:pk>/updates/<int:update_id>/", SignalUpdateDetailView.as_view(), name="signal-update-detail"),
    path(
        "legacy/my-signals/",
        TraderSignalListView.as_view(),
        name="trader-signals",
    ),

    path(
        "legacy/pending/",
        PendingSignalListView.as_view(),
        name="pending-signals",
    ),

    path(
        "legacy/",
        SignalListCreateView.as_view(),
        name="signal-list-create",
    ),

    path(
        "legacy/<int:pk>/",
        SignalDetailView.as_view(),
        name="signal-detail",
    ),

    path(
        "legacy/<int:pk>/approve/",
        ApproveSignalView.as_view(),
        name="signal-approve",
    ),

    path(
        "legacy/<int:pk>/reject/",
        RejectSignalView.as_view(),
        name="signal-reject",
    ),
]
