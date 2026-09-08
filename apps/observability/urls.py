from django.urls import path

from .views import (
    FrontendLogIngestView, LogEventDetailView, LogEventListView,
    LogEventPurgeView, LogEventResolveView, LogSummaryView,
)


urlpatterns = [
    path("frontend/", FrontendLogIngestView.as_view(), name="frontend-log-ingest"),
    path("logs/", LogEventListView.as_view(), name="observability-log-list"),
    path("logs/summary/", LogSummaryView.as_view(), name="observability-log-summary"),
    path("logs/purge/", LogEventPurgeView.as_view(), name="observability-log-purge"),
    path("logs/<int:pk>/", LogEventDetailView.as_view(), name="observability-log-detail"),
    path("logs/<int:pk>/resolve/", LogEventResolveView.as_view(), name="observability-log-resolve"),
]
