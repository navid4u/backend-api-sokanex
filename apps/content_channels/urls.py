from django.urls import path
from .views import (
    ChannelPostDetailView, ChannelTicketView, InternalAnalysisChannelView,
    InternalAnalysisManageDetailView, InternalAnalysisManageListCreateView,
    InternalAnalysisViewCountView, VIPSignalChannelView,
)

urlpatterns = [
    path("vip-signals/", VIPSignalChannelView.as_view(), name="vip-signal-channel"),
    path("internal-analysis/", InternalAnalysisChannelView.as_view(), name="internal-analysis-channel"),
    path("internal-analysis/manage/", InternalAnalysisManageListCreateView.as_view(), name="internal-analysis-manage"),
    path("internal-analysis/manage/<int:pk>/", InternalAnalysisManageDetailView.as_view(), name="internal-analysis-manage-detail"),
    path("internal-analysis/<int:pk>/view/", InternalAnalysisViewCountView.as_view(), name="internal-analysis-view"),
    path("posts/<int:pk>/", ChannelPostDetailView.as_view(), name="channel-post-detail"),
    path("ticket/", ChannelTicketView.as_view(), name="channel-ticket"),
]
