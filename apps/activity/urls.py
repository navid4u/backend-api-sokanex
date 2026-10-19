from django.urls import path

from .views import PageViewIngestView, RecentActivityListView

urlpatterns = [
    path("recent/", RecentActivityListView.as_view(), name="recent-activity"),
    path("page-views/", PageViewIngestView.as_view(), name="page-view-ingest"),
]

