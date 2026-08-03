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
    SupportMessageListCreateView,
    SupportThreadView,
)


urlpatterns = [
    path("support/", SupportThreadView.as_view(), name="support-thread"),
    path("support/messages/", SupportMessageListCreateView.as_view(), name="support-messages"),
    path("social/feed/", SocialFeedView.as_view(), name="social-feed"),
    path("social/saved/", SavedPostListView.as_view(), name="social-saved"),
    path("social/following/", FollowingListView.as_view(), name="social-following"),
    path("social/users/<int:user_id>/follow/", FollowUserView.as_view(), name="social-follow-user"),
    path("social/posts/<int:pk>/", SocialPostDetailView.as_view(), name="social-post-detail"),
    path("social/posts/<int:pk>/comments/", PostCommentListCreateView.as_view(), name="social-post-comments"),
    path("social/posts/<int:pk>/reaction/", PostReactionView.as_view(), name="social-post-reaction"),
    path("social/posts/<int:pk>/save/", SavePostView.as_view(), name="social-post-save"),
    path("social/posts/<int:pk>/report/", ReportPostView.as_view(), name="social-post-report"),
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

    path(
        "<str:slug>/",
        ChatRoomDetailView.as_view(),
        name="chat-room-detail",
    ),
]
