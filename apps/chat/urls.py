from django.urls import path

from .views import (
    ChatRoomDetailView,
    ChatRoomListCreateView,
    DeleteMessageView,
    JoinChatRoomView,
    LeaveChatRoomView,
    RoomMessageListCreateView,
)


urlpatterns = [
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