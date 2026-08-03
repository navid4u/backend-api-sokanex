from django.urls import path
from .views import ChannelPostDetailView, ChannelTicketView, InternalAnalysisChannelView, VIPSignalChannelView

urlpatterns = [
    path("vip-signals/", VIPSignalChannelView.as_view(), name="vip-signal-channel"),
    path("internal-analysis/", InternalAnalysisChannelView.as_view(), name="internal-analysis-channel"),
    path("posts/<int:pk>/", ChannelPostDetailView.as_view(), name="channel-post-detail"),
    path("ticket/", ChannelTicketView.as_view(), name="channel-ticket"),
]
