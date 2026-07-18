from django.shortcuts import get_object_or_404

from drf_spectacular.utils import (
    extend_schema,
    inline_serializer,
)
from rest_framework import (
    generics,
    serializers,
    status,
)
from rest_framework.filters import (
    OrderingFilter,
    SearchFilter,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import IsEmployee

from .models import ChatRoom, Message
from .serializers import (
    ChatRoomSerializer,
    ChatRoomWriteSerializer,
    MessageSerializer,
)
from .services import ChatService


class ChatRoomListCreateView(
    generics.ListCreateAPIView
):

    filter_backends = [
        SearchFilter,
        OrderingFilter,
    ]

    search_fields = [
        "name",
        "description",
    ]

    ordering_fields = [
        "name",
        "created_at",
    ]

    def get_permissions(self):
        permissions = [IsAuthenticated()]

        if self.request.method == "POST":
            permissions.append(IsEmployee())

        return permissions

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ChatRoomWriteSerializer

        return ChatRoomSerializer

    def get_queryset(self):
        if getattr(
            self,
            "swagger_fake_view",
            False,
        ):
            return ChatRoom.objects.none()

        return ChatService.visible_rooms(
            self.request.user
        )

    def perform_create(self, serializer):
        ChatService.create_room(
            serializer,
            self.request.user,
        )


class ChatRoomDetailView(
    generics.RetrieveUpdateDestroyAPIView
):

    lookup_field = "slug"

    def get_permissions(self):
        permissions = [IsAuthenticated()]

        if self.request.method in [
            "PUT",
            "PATCH",
            "DELETE",
        ]:
            permissions.append(IsEmployee())

        return permissions

    def get_serializer_class(self):
        if self.request.method in [
            "PUT",
            "PATCH",
        ]:
            return ChatRoomWriteSerializer

        return ChatRoomSerializer

    def get_queryset(self):
        if getattr(
            self,
            "swagger_fake_view",
            False,
        ):
            return ChatRoom.objects.none()

        return ChatService.visible_rooms(
            self.request.user
        )


class JoinChatRoomView(APIView):

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None,
        responses=inline_serializer(
            name="JoinChatRoomResponse",
            fields={
                "message": serializers.CharField(),
                "membership_role": (
                    serializers.CharField()
                ),
            },
        ),
    )
    def post(self, request, slug):
        room = get_object_or_404(
            ChatRoom,
            slug=slug,
            is_active=True,
        )

        membership = ChatService.join_room(
            room,
            request.user,
        )

        return Response(
            {
                "message": "Joined chat room.",
                "membership_role": membership.role,
            },
            status=status.HTTP_200_OK,
        )


class LeaveChatRoomView(APIView):

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None,
        responses=inline_serializer(
            name="LeaveChatRoomResponse",
            fields={
                "message": serializers.CharField(),
            },
        ),
    )
    def post(self, request, slug):
        room = get_object_or_404(
            ChatRoom,
            slug=slug,
            is_active=True,
        )

        ChatService.leave_room(
            room,
            request.user,
        )

        return Response(
            {
                "message": "Left chat room.",
            },
            status=status.HTTP_200_OK,
        )


class RoomMessageListCreateView(
    generics.ListCreateAPIView
):

    permission_classes = [IsAuthenticated]

    serializer_class = MessageSerializer

    def get_room(self):
        return get_object_or_404(
            ChatRoom,
            slug=self.kwargs["slug"],
            is_active=True,
        )

    def get_queryset(self):
        if getattr(
            self,
            "swagger_fake_view",
            False,
        ):
            return Message.objects.none()

        room = self.get_room()

        ChatService.ensure_member(
            room,
            self.request.user,
        )

        return ChatService.room_messages(room)

    def perform_create(self, serializer):
        room = self.get_room()

        ChatService.ensure_member(
            room,
            self.request.user,
        )

        ChatService.create_message(
            serializer,
            room,
            self.request.user,
        )


class DeleteMessageView(APIView):

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None,
        responses={204: None},
    )
    def delete(self, request, pk):
        message = get_object_or_404(
            Message.objects.select_related(
                "room",
                "sender",
            ),
            pk=pk,
        )

        ChatService.delete_message(
            message,
            request.user,
        )

        return Response(
            status=status.HTTP_204_NO_CONTENT
        )