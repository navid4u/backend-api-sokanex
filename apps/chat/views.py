from django.shortcuts import get_object_or_404
from django.db.models import Count, Exists, OuterRef, Q

from drf_spectacular.utils import (
    extend_schema,
    inline_serializer,
)
from django_filters.rest_framework import (
    DjangoFilterBackend,
)
from .filters import MessageFilter
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
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import CursorPagination
from django.utils import timezone
from django.core import signing
from django.conf import settings
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from common.serializers import EmptySerializer
from common.throttles import SupportMessageRateThrottle

from common.permissions import IsEmployee

from .models import (
    ChatRoom, Message, PostComment, PostReaction, PostReport,
    SavedPost, SupportMessage, SupportThread, TraderPost, UserFollow,
)
from .serializers import (
    ChatRoomSerializer,
    ChatRoomWriteSerializer,
    MessageSerializer,
    FollowSerializer,
    PostCommentSerializer,
    PostReactionSerializer,
    PostReportSerializer,
    TraderPostSerializer,
    SupportMessageSerializer,
    SupportThreadSerializer,
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

    filterset_class = MessageFilter

    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]

    search_fields = [
        "text",
        "sender__username",
        "reply_to__text",
    ]

    ordering_fields = [
        "created_at",
        "updated_at",
        "sender__username",
    ]

    ordering = [
        "-created_at",
        "-id",
    ]

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        requested = self.request.query_params.get("ordering", "")
        terms = [term.strip() for term in requested.split(",") if term.strip()]
        allowed = {field for field in self.ordering_fields}
        if terms and all(term.lstrip("-") in allowed for term in terms):
            tie_breaker = "-id" if terms[-1].startswith("-") else "id"
            return queryset.order_by(*terms, tie_breaker)
        return queryset

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


def social_posts_for(user):
    following_ids = UserFollow.objects.filter(follower=user).values("following_id")
    queryset = TraderPost.objects.filter(is_deleted=False).filter(
        Q(visibility=TraderPost.Visibility.PUBLIC)
        | Q(author=user)
        | Q(visibility=TraderPost.Visibility.FOLLOWERS, author_id__in=following_ids)
    )
    return queryset.select_related("author").annotate(
        reactions_count=Count("reactions", distinct=True),
        comments_count=Count("comments", filter=Q(comments__is_deleted=False), distinct=True),
        is_reacted=Exists(PostReaction.objects.filter(post=OuterRef("pk"), user=user)),
        is_saved=Exists(SavedPost.objects.filter(post=OuterRef("pk"), user=user)),
    )


class SocialFeedView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TraderPostSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["text", "author__username", "author__first_name", "author__last_name"]
    ordering_fields = ["created_at", "updated_at"]

    def get_queryset(self):
        queryset = social_posts_for(self.request.user)
        if self.request.query_params.get("following") == "true":
            followed = UserFollow.objects.filter(follower=self.request.user).values("following_id")
            queryset = queryset.filter(author_id__in=followed)
        return queryset

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)


class SocialPostDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TraderPostSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        return social_posts_for(self.request.user)

    def perform_update(self, serializer):
        if serializer.instance.author_id != self.request.user.id:
            raise serializers.ValidationError("Only the post author can edit this post.")
        serializer.save(is_edited=True)

    def perform_destroy(self, instance):
        if instance.author_id != self.request.user.id and not self.request.user.is_staff:
            raise serializers.ValidationError("Only the author or a moderator can delete this post.")
        instance.is_deleted = True
        instance.save(update_fields=["is_deleted", "updated_at"])


class PostCommentListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PostCommentSerializer

    def get_post(self):
        return get_object_or_404(social_posts_for(self.request.user), pk=self.kwargs["pk"])

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return PostComment.objects.none()
        return PostComment.objects.filter(post=self.get_post(), is_deleted=False).select_related("author")

    def perform_create(self, serializer):
        serializer.save(post=self.get_post(), author=self.request.user)


class PostReactionView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PostReactionSerializer

    def post(self, request, pk):
        post = get_object_or_404(social_posts_for(request.user), pk=pk)
        serializer = PostReactionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reaction, _ = PostReaction.objects.update_or_create(
            post=post, user=request.user, defaults=serializer.validated_data
        )
        return Response(PostReactionSerializer(reaction).data)

    def delete(self, request, pk):
        PostReaction.objects.filter(post_id=pk, user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SavePostView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TraderPostSerializer

    def post(self, request, pk):
        post = get_object_or_404(social_posts_for(request.user), pk=pk)
        SavedPost.objects.get_or_create(user=request.user, post=post)
        return Response({"message": "Post saved."})

    def delete(self, request, pk):
        SavedPost.objects.filter(user=request.user, post_id=pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SavedPostListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TraderPostSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return TraderPost.objects.none()
        return social_posts_for(self.request.user).filter(saves__user=self.request.user)


class FollowUserView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = FollowSerializer

    def post(self, request, user_id):
        if request.user.id == user_id:
            raise serializers.ValidationError("You cannot follow yourself.")
        target = get_object_or_404(request.user.__class__, pk=user_id, is_active=True)
        UserFollow.objects.get_or_create(follower=request.user, following=target)
        return Response({"message": "User followed."})

    def delete(self, request, user_id):
        UserFollow.objects.filter(follower=request.user, following_id=user_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class FollowingListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = FollowSerializer
    pagination_class = None

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return UserFollow.objects.none()
        return UserFollow.objects.filter(follower=self.request.user).select_related("following")


class ReportPostView(generics.CreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PostReportSerializer

    def perform_create(self, serializer):
        post = get_object_or_404(social_posts_for(self.request.user), pk=self.kwargs["pk"])
        serializer.save(post=post, reporter=self.request.user)


class SupportThreadView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SupportThreadSerializer

    def get_thread(self, request):
        user = request.user
        requested_user_id = request.query_params.get("user_id")
        if requested_user_id and (user.is_staff or user.role in (user.Role.ADMIN, user.Role.SUPER_ADMIN, user.Role.EMPLOYEE)):
            target = get_object_or_404(user.__class__, pk=requested_user_id)
        else:
            target = user
        thread, _ = SupportThread.objects.get_or_create(user=target)
        return thread

    def get(self, request):
        return Response(SupportThreadSerializer(self.get_thread(request), context={"request": request}).data)


class SupportMessageListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SupportMessageSerializer

    def get_thread(self):
        helper = SupportThreadView()
        return helper.get_thread(self.request)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return SupportMessage.objects.none()
        return SupportMessage.objects.filter(thread=self.get_thread()).select_related("sender")

    def perform_create(self, serializer):
        thread = self.get_thread()
        if thread.is_closed:
            raise serializers.ValidationError("This support conversation is closed.")
        serializer.save(thread=thread, sender=self.request.user)


def support_staff(user):
    return user.is_staff or user.role in (user.Role.EMPLOYEE, user.Role.ADMIN, user.Role.SUPER_ADMIN)


def support_thread_for(user, pk):
    queryset = SupportThread.objects.select_related("user", "assigned_to")
    return get_object_or_404(queryset, pk=pk) if support_staff(user) else get_object_or_404(queryset, pk=pk, user=user)


class SupportCursorPagination(CursorPagination):
    page_size = 30
    ordering = "-created_at"


class SupportConversationView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SupportThreadSerializer

    def get(self, request):
        thread, _ = SupportThread.objects.get_or_create(user=request.user)
        return Response(SupportThreadSerializer(thread, context={"request": request}).data)


class SupportConversationMessageView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SupportMessageSerializer
    pagination_class = SupportCursorPagination

    def get_throttles(self):
        return [SupportMessageRateThrottle()] if self.request.method == "POST" else []

    def get_thread(self):
        return support_thread_for(self.request.user, self.kwargs["pk"])

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return SupportMessage.objects.none()
        return SupportMessage.objects.filter(thread=self.get_thread()).select_related("sender")

    def perform_create(self, serializer):
        thread = self.get_thread()
        if thread.is_closed:
            raise serializers.ValidationError("This support conversation is closed.")
        message = serializer.save(thread=thread, sender=self.request.user, delivered_at=timezone.now())
        payload = SupportMessageSerializer(message, context={"request": self.request}).data
        async_to_sync(get_channel_layer().group_send)(
            f"support_{thread.pk}", {"type": "support.event", "payload": {"type": "message.created", "data": payload}}
        )


class SupportConversationReadView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EmptySerializer

    def post(self, request, pk):
        thread = support_thread_for(request.user, pk)
        SupportMessage.objects.filter(thread=thread, read_at__isnull=True).exclude(sender=request.user).update(read_at=timezone.now())
        return Response({"read": True})


class SupportQueueView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SupportThreadSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False) or not support_staff(self.request.user):
            return SupportThread.objects.none()
        return SupportThread.objects.filter(is_closed=False).select_related("user", "assigned_to").order_by("updated_at")


class SupportTicketView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EmptySerializer

    def post(self, request, pk):
        thread = support_thread_for(request.user, pk)
        ticket = signing.dumps(
            {"user_id": request.user.pk, "thread_id": thread.pk},
            salt="support-ws-ticket", compress=True,
        )
        return Response({"ticket": ticket, "expires_in": settings.CHANNEL_TICKET_TTL_SECONDS})
