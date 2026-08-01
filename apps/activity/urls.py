from django.urls import path

from .views import RecentActivityListView

urlpatterns = [
    path("recent/", RecentActivityListView.as_view(), name="recent-activity"),
]

