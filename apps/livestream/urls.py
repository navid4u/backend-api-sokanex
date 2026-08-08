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
    LiveEventStartView,
    LiveEventEndView,
    LiveRecordingListStartView,
    LiveRecordingStopView,
    LiveChatMessageDeleteView,
    LiveKitWebhookView,
)


urlpatterns = [
    path("webhooks/livekit/", LiveKitWebhookView.as_view(), name="livekit-webhook"),
    path("<str:slug>/join/", LiveJoinView.as_view(), name="live-join"),
    path("<str:slug>/chat/", LiveChatView.as_view(), name="live-chat"),
    path("<str:slug>/chat/<int:message_id>/", LiveChatMessageDeleteView.as_view(), name="live-chat-delete"),
    path("<str:slug>/ticket/", LiveTicketView.as_view(), name="live-ticket"),
    path("<str:slug>/start/", LiveEventStartView.as_view(), name="live-start"),
    path("<str:slug>/end/", LiveEventEndView.as_view(), name="live-end"),
    path("<str:slug>/recordings/", LiveRecordingListStartView.as_view(), name="live-recording-list-start"),
    path("<str:slug>/recordings/<int:recording_id>/stop/", LiveRecordingStopView.as_view(), name="live-recording-stop"),
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
