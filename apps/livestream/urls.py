from django.urls import path

from .views import (
    LiveEventDetailView,
    LiveEventListCreateView,
    LiveEventManagementListView,
    LivePresenceView,
    SpeakRequestCreateView,
    SpeakRequestReviewView,
    ParticipantMuteView,
    ParticipantRemoveView,
    LiveJoinView,
    LiveChatView,
    LiveTicketView,
)


urlpatterns = [
    path("<str:slug>/join/", LiveJoinView.as_view(), name="live-join"),
    path("<str:slug>/chat/", LiveChatView.as_view(), name="live-chat"),
    path("<str:slug>/ticket/", LiveTicketView.as_view(), name="live-ticket"),
    path("<str:slug>/presence/", LivePresenceView.as_view(), name="live-presence"),
    path("<str:slug>/speak-requests/", SpeakRequestCreateView.as_view(), name="live-speak-request"),
    path("<str:slug>/speak-requests/<int:request_id>/", SpeakRequestReviewView.as_view(), name="live-speak-request-review"),
    path("<str:slug>/participants/<int:participant_id>/mute/", ParticipantMuteView.as_view(), name="live-participant-mute"),
    path("<str:slug>/participants/<int:participant_id>/", ParticipantRemoveView.as_view(), name="live-participant-remove"),
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
