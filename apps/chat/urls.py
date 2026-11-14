from django.urls import path

from .views import (
    ChatRoomDetailView,
    ChatRoomListCreateView,
    DeleteMessageView,
    JoinChatRoomView,
    LeaveChatRoomView,
    RoomMessageListCreateView,
    FollowingListView,
    FollowUserView,
    PostCommentListCreateView,
    PostReactionView,
    ReportPostView,
    SavePostView,
    SavedPostListView,
    SocialFeedView,
    SocialPostDetailView,
    SocialPostMediaView,
    SupportMessageListCreateView,
    SupportThreadView,
    TopContributorsView,
    SocialUserDetailView,
    SocialUserPostListView,
)
from .social_extra import (
    AnalystListView, AnalystManageDetailView, AnalystManageListView, CommentReportView,
    CommunityView, PollVoteView, PostCommentDetailView, PostUsefulView,
    ReportManageDetailView, ReportManageListView, RoomInvitationAcceptView,
    RoomInvitationView, RoomPresenceView,
)


urlpatterns = [
    path("support/", SupportThreadView.as_view(), name="support-thread"),
    path("support/messages/", SupportMessageListCreateView.as_view(), name="support-messages"),
    path("social/feed/", SocialFeedView.as_view(), name="social-feed"),
    path("social/community/", CommunityView.as_view(), name="social-community"),
    path("social/analysts/", AnalystListView.as_view(), name="social-analysts"),
    path("social/manage/analysts/", AnalystManageListView.as_view(), name="social-manage-analysts"),
    path("social/manage/analysts/<int:user_id>/", AnalystManageDetailView.as_view(), name="social-manage-analyst-detail"),
    path("social/manage/reports/", ReportManageListView.as_view(), name="social-manage-reports"),
    path("social/manage/reports/<int:report_id>/", ReportManageDetailView.as_view(), name="social-manage-report-detail"),
    path("social/saved/", SavedPostListView.as_view(), name="social-saved"),
    path("social/following/", FollowingListView.as_view(), name="social-following"),
    path("social/users/top-contributors/", TopContributorsView.as_view(), name="social-top-contributors"),
    path("social/users/<int:user_id>/", SocialUserDetailView.as_view(), name="social-user-detail"),
    path("social/users/<int:user_id>/posts/", SocialUserPostListView.as_view(), name="social-user-posts"),
    path("social/users/<int:user_id>/follow/", FollowUserView.as_view(), name="social-follow-user"),
    path("social/posts/<int:pk>/", SocialPostDetailView.as_view(), name="social-post-detail"),
    path("social/posts/<int:pk>/media/<str:kind>/", SocialPostMediaView.as_view(), name="social-post-media"),
    path("social/posts/<int:pk>/comments/", PostCommentListCreateView.as_view(), name="social-post-comments"),
    path("social/comments/<int:pk>/", PostCommentDetailView.as_view(), name="social-comment-detail"),
    path("social/comments/<int:pk>/report/", CommentReportView.as_view(), name="social-comment-report"),
    path("social/posts/<int:pk>/useful/", PostUsefulView.as_view(), name="social-post-useful"),
    path("social/posts/<int:pk>/poll/vote/", PollVoteView.as_view(), name="social-post-poll-vote"),
    path("social/posts/<int:pk>/reaction/", PostReactionView.as_view(), name="social-post-reaction"),
    path("social/posts/<int:pk>/save/", SavePostView.as_view(), name="social-post-save"),
    path("social/posts/<int:pk>/report/", ReportPostView.as_view(), name="social-post-report"),
    path("invitations/<int:invitation_id>/accept/", RoomInvitationAcceptView.as_view(), name="chat-room-invitation-accept"),
    path(
        "",
        ChatRoomListCreateView.as_view(),
        name="chat-room-list-create",
    ),

    path(
        "messages/<int:pk>/",
        DeleteMessageView.as_view(),
        name="chat-message-delete",
    ),

    path(
        "<str:slug>/join/",
        JoinChatRoomView.as_view(),
        name="chat-room-join",
    ),

    path(
        "<str:slug>/leave/",
        LeaveChatRoomView.as_view(),
        name="chat-room-leave",
    ),

    path(
        "<str:slug>/messages/",
        RoomMessageListCreateView.as_view(),
        name="chat-room-messages",
    ),
    path("<str:slug>/presence/", RoomPresenceView.as_view(), name="chat-room-presence"),
    path("<str:slug>/invitations/", RoomInvitationView.as_view(), name="chat-room-invitations"),

    path(
        "<str:slug>/",
        ChatRoomDetailView.as_view(),
        name="chat-room-detail",
    ),
]
