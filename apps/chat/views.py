from django.shortcuts import get_object_or_404
from django.db.models import Count, Exists, OuterRef, Prefetch, Q
from django.db import transaction
from django.http import Http404, HttpResponse, StreamingHttpResponse
from django.utils.cache import patch_vary_headers
from pathlib import Path
import mimetypes
import re

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
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from common.pagination import DefaultPagination
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
    SavedPost, SupportMessage, SupportThread, TraderPost, UserFollow, PostUseful,
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
    SupportThreadUpdateSerializer,
    SocialUserSerializer,
)
from .services import ChatService
from .throttles import SocialWriteThrottle, SocialReportThrottle
from apps.notifications.models import Notification
from apps.notifications.services import NotificationService


class ChatRoomListCreateView(
    generics.ListCreateAPIView
):

    def is_manage_request(self):
        return self.request.query_params.get("manage", "").lower() == "true"

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

        if self.request.method == "POST" or self.is_manage_request():
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

        queryset = ChatService.manageable_rooms(self.request.user) if self.is_manage_request() else ChatService.visible_rooms(self.request.user)
        market = self.request.query_params.get("market")
        if market:
            if market not in TraderPost.Market.values:
                raise ValidationError({"market": "Unknown market."})
            queryset = queryset.filter(market=market)
        return queryset.select_related("manager")

    def perform_create(self, serializer):
        ChatService.create_room(
            serializer,
            self.request.user,
        )


class ChatRoomDetailView(
    generics.RetrieveUpdateDestroyAPIView
):

    lookup_field = "slug"

    def is_manage_request(self):
        return self.request.query_params.get("manage", "").lower() == "true"

    def get_permissions(self):
        permissions = [IsAuthenticated()]

        if self.request.method in [
            "PUT",
            "PATCH",
            "DELETE",
        ] or self.is_manage_request():
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

        if self.request.method in ["PUT", "PATCH", "DELETE"] or self.is_manage_request():
            return ChatService.manageable_rooms(self.request.user).select_related("manager")

        return ChatService.visible_rooms(self.request.user).select_related("manager")

    def perform_update(self, serializer):
        room = serializer.save()
        if not room.is_active:
            from .community import clear_presence
            clear_presence(room)


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
        from .community import clear_presence
        clear_presence(room, request.user)

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


def _chat_media_response(request, field, legacy_prefix):
    try:
        file_obj = field.storage.open(field.name, "rb")
    except FileNotFoundError:
        # Existing public files are not moved by the storage migration.
        legacy_root = Path(settings.MEDIA_ROOT).resolve()
        legacy_path = (legacy_root / field.name).resolve()
        if not field.name.startswith(legacy_prefix) or not legacy_path.is_relative_to(legacy_root) or not legacy_path.is_file():
            raise Http404 from None
        file_obj = legacy_path.open("rb")
    size = file_obj.seek(0, 2)
    file_obj.seek(0)
    start, end = 0, size - 1
    requested_range = request.headers.get("Range", "")
    if requested_range:
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", requested_range)
        if not match or (not match.group(1) and not match.group(2)):
            file_obj.close()
            response = HttpResponse(status=416)
            response["Content-Range"] = f"bytes */{size}"
            return response
        if match.group(1):
            start = int(match.group(1))
            end = min(int(match.group(2)), size - 1) if match.group(2) else size - 1
        else:
            start = max(size - int(match.group(2)), 0)
        if start > end or start >= size:
            file_obj.close()
            response = HttpResponse(status=416)
            response["Content-Range"] = f"bytes */{size}"
            return response
        file_obj.seek(start)
    response = StreamingHttpResponse(
        _social_media_chunks(file_obj, end - start + 1),
        status=206 if requested_range else 200,
        content_type=mimetypes.guess_type(field.name)[0] or "application/octet-stream",
    )
    response["Content-Length"] = str(end - start + 1)
    response["Accept-Ranges"] = "bytes"
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    patch_vary_headers(response, ["Authorization"])
    if requested_range:
        response["Content-Range"] = f"bytes {start}-{end}/{size}"
    return response


class ChatRoomImageView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        room = get_object_or_404(ChatRoom, pk=pk)
        can_manage = IsEmployee().has_permission(request, self)
        can_view = room.is_active and (
            room.is_public or room.members.filter(pk=request.user.pk).exists()
        )
        if not (can_manage or can_view) or not room.image:
            raise Http404
        return _chat_media_response(request, room.image, "chat/rooms/")


class ChatMessageAttachmentView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        message = get_object_or_404(Message.objects.select_related("room"), pk=pk, is_deleted=False)
        if not message.room.is_active or not message.room.members.filter(pk=request.user.pk).exists() or not message.attachment:
            raise Http404
        return _chat_media_response(request, message.attachment, "chat/attachments/")


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
        useful_count=Count("useful_votes", distinct=True),
        is_reacted=Exists(PostReaction.objects.filter(post=OuterRef("pk"), user=user)),
        is_saved=Exists(SavedPost.objects.filter(post=OuterRef("pk"), user=user)),
        is_useful=Exists(PostUseful.objects.filter(post=OuterRef("pk"), user=user)),
    )


def social_users_for(queryset, viewer):
    followed = UserFollow.objects.filter(follower=viewer).values("following_id")
    visible = Q(social_posts__visibility=TraderPost.Visibility.PUBLIC) | Q(pk=viewer.pk) | Q(
        pk__in=followed, social_posts__visibility=TraderPost.Visibility.FOLLOWERS
    )
    return queryset.annotate(
        visible_posts_count=Count("social_posts", filter=Q(social_posts__is_deleted=False) & visible, distinct=True),
        followers_count=Count("follower_relations", distinct=True),
        following_count=Count("following_relations", distinct=True),
        followed_by_viewer=Exists(UserFollow.objects.filter(follower=viewer, following_id=OuterRef("pk"))),
    )


class SocialFeedView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [SocialWriteThrottle]
    serializer_class = TraderPostSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    filter_backends = []
    search_fields = ["text"]
    ordering_fields = ["created_at", "updated_at"]
    ordering = ["-created_at", "-id"]

    class Pagination(CursorPagination):
        page_size = 20
        page_size_query_param = "page_size"
        max_page_size = 100
        ordering = ("-created_at", "-id")

    pagination_class = Pagination

    def get_queryset(self):
        queryset = social_posts_for(self.request.user)
        from .social_v3 import filter_social_posts
        queryset = filter_social_posts(queryset, self.request)
        return queryset

    def list(self, request, *args, **kwargs):
        from .social_v3 import paginated_social_posts
        return paginated_social_posts(self.get_queryset(), request, self.get_serializer)

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)


class SocialPostDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TraderPostSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        if self.request.method in ("PATCH", "DELETE") and can_moderate_social(self.request.user):
            return TraderPost.objects.filter(is_deleted=False)
        return social_posts_for(self.request.user)

    def perform_update(self, serializer):
        if serializer.instance.author_id != self.request.user.id and not can_moderate_social(self.request.user):
            raise PermissionDenied("Only the post author or content manager can edit this post.")
        serializer.save(is_edited=True)

    def perform_destroy(self, instance):
        if instance.author_id != self.request.user.id and not can_moderate_social(self.request.user):
            raise PermissionDenied("Only the author or a moderator can delete this post.")
        instance.is_deleted = True
        instance.save(update_fields=["is_deleted", "updated_at"])


def can_moderate_social(user):
    return bool(user.is_staff or user.is_superuser or user.has_platform_permission(user.Permission.CONTENT_MANAGE))


def _social_media_chunks(file_obj, remaining):
    try:
        while remaining:
            chunk = file_obj.read(min(64 * 1024, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk
    finally:
        file_obj.close()


class SocialPostMediaView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, kind):
        if kind not in ("image", "video"):
            raise Http404
        post = get_object_or_404(social_posts_for(request.user), pk=pk)
        field = getattr(post, kind)
        if not field:
            raise Http404
        try:
            file_obj = field.storage.open(field.name, "rb")
        except FileNotFoundError:
            # Older files can remain in MEDIA_ROOT. The origin/CDN must deny
            # direct /media/social/posts/ to close that legacy bypass.
            legacy_root = Path(settings.MEDIA_ROOT).resolve()
            legacy_path = (legacy_root / field.name).resolve()
            if not field.name.startswith("social/posts/") or not legacy_path.is_relative_to(legacy_root) or not legacy_path.is_file():
                raise Http404 from None
            file_obj = legacy_path.open("rb")
        size = file_obj.seek(0, 2)
        file_obj.seek(0)
        start, end = 0, size - 1
        requested_range = request.headers.get("Range", "")
        if requested_range:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", requested_range)
            if not match or (not match.group(1) and not match.group(2)):
                file_obj.close()
                response = HttpResponse(status=416)
                response["Content-Range"] = f"bytes */{size}"
                return response
            if match.group(1):
                start = int(match.group(1))
                end = min(int(match.group(2)), size - 1) if match.group(2) else size - 1
            else:
                start = max(size - int(match.group(2)), 0)
            if start > end or start >= size:
                file_obj.close()
                response = HttpResponse(status=416)
                response["Content-Range"] = f"bytes */{size}"
                return response
            file_obj.seek(start)
        content_type = mimetypes.guess_type(field.name)[0] or "application/octet-stream"
        response = StreamingHttpResponse(
            _social_media_chunks(file_obj, end - start + 1),
            status=206 if requested_range else 200,
            content_type=content_type,
        )
        response["Content-Length"] = str(end - start + 1)
        response["Accept-Ranges"] = "bytes"
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        patch_vary_headers(response, ["Authorization"])
        if requested_range:
            response["Content-Range"] = f"bytes {start}-{end}/{size}"
        return response


class TopContributorsView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SocialUserSerializer
    pagination_class = None

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            from apps.accounts.models import User
            return User.objects.none()
        limit = min(max(int(self.request.query_params.get("limit", 10)), 1), 50)
        return social_users_for(self.request.user.__class__.objects.filter(is_active=True), self.request.user).order_by("-visible_posts_count", "id")[:limit]


class SocialUserDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SocialUserSerializer
    lookup_url_kwarg = "user_id"

    def get_queryset(self):
        return social_users_for(self.request.user.__class__.objects.filter(is_active=True), self.request.user)


class SocialUserPostListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TraderPostSerializer
    filter_backends = [OrderingFilter]
    ordering_fields = ["created_at", "updated_at"]
    ordering = ["-created_at", "-id"]

    def get_queryset(self):
        queryset = social_posts_for(self.request.user).filter(
            author_id=self.kwargs["user_id"]
        )
        post_type = self.request.query_params.get("post_type")
        if post_type:
            if post_type not in TraderPost.Type.values:
                raise ValidationError({"post_type": "Unknown post type."})
            queryset = queryset.filter(post_type=post_type)
        return queryset.order_by("-created_at", "-id")

    def list(self, request, *args, **kwargs):
        from .social_v3 import paginated_social_posts
        return paginated_social_posts(self.get_queryset(), request, self.get_serializer, extra_filter={"author_id": self.kwargs["user_id"], "post_type": request.query_params.get("post_type", "")})


class PostCommentListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [SocialWriteThrottle]
    serializer_class = PostCommentSerializer
    ordering = ["created_at", "id"]
    pagination_class = DefaultPagination

    def get_post(self):
        return get_object_or_404(social_posts_for(self.request.user), pk=self.kwargs["pk"])

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return PostComment.objects.none()
        ordering = self.request.query_params.get("ordering", "created_at")
        if ordering not in ("created_at", "-created_at"):
            raise ValidationError({"ordering": "Unknown ordering."})
        return PostComment.objects.filter(post=self.get_post(), is_deleted=False).select_related("author", "parent").order_by(ordering, "id" if ordering == "created_at" else "-id")

    def list(self, request, *args, **kwargs):
        from .social_v3 import enrich_social_authors
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            enrich_social_authors(request, page)
            return self.get_paginated_response(self.get_serializer(page, many=True).data)
        rows = list(queryset)
        enrich_social_authors(request, rows)
        return Response(self.get_serializer(rows, many=True).data)

    def perform_create(self, serializer):
        post = self.get_post()
        parent = serializer.validated_data.get("parent")
        if parent and (parent.post_id != post.pk or parent.is_deleted):
            raise ValidationError({"reply_to": "Reply must belong to this post."})
        with transaction.atomic():
            comment = serializer.save(post=post, author=self.request.user)
            if post.author_id != self.request.user.pk and (not parent or post.author_id != parent.author_id):
                from .community import queue_social_notification
                transaction.on_commit(lambda: queue_social_notification(key=f"COMMENT:{comment.pk}", recipient_id=post.author_id, title="نظر جدید برای پست شما", url=f"/chat?post={post.pk}"))
            if parent and parent.author_id != self.request.user.pk:
                from .community import queue_social_notification
                transaction.on_commit(lambda: queue_social_notification(key=f"REPLY:{comment.pk}", recipient_id=parent.author_id, title="پاسخ جدید به نظر شما", url=f"/chat?post={post.pk}"))


class PostReactionView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [SocialWriteThrottle]
    serializer_class = PostReactionSerializer

    def post(self, request, pk):
        post = get_object_or_404(social_posts_for(request.user), pk=pk)
        serializer = PostReactionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reaction, created = PostReaction.objects.update_or_create(
            post=post, user=request.user, defaults=serializer.validated_data
        )
        if created and post.author_id != request.user.pk:
            from .community import queue_social_notification
            transaction.on_commit(lambda: queue_social_notification(key=f"LIKE:{reaction.pk}", recipient_id=post.author_id, title="واکنش جدید به پست شما", url=f"/chat?post={post.pk}"))
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
        return social_posts_for(self.request.user).filter(saves__user=self.request.user).order_by("-created_at", "-id")


class FollowUserView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [SocialWriteThrottle]
    serializer_class = FollowSerializer

    def post(self, request, user_id):
        if request.user.id == user_id:
            raise serializers.ValidationError("You cannot follow yourself.")
        target = get_object_or_404(request.user.__class__, pk=user_id, is_active=True)
        relation, created = UserFollow.objects.get_or_create(follower=request.user, following=target)
        if created:
            from .community import queue_social_notification
            transaction.on_commit(lambda: queue_social_notification(key=f"FOLLOW:{relation.pk}", recipient_id=target.pk, title="دنبال‌کنندهٔ جدید", url=f"/chat/users/{request.user.pk}"))
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
    throttle_classes = [SocialReportThrottle]
    serializer_class = PostReportSerializer

    def create(self, request, *args, **kwargs):
        from .social_extra import _report_data
        post = get_object_or_404(social_posts_for(request.user), pk=self.kwargs["pk"])
        reason, description = _report_data(request)
        report, created = PostReport.objects.get_or_create(
            post=post, reporter=request.user, defaults={"reason": reason, "description": description}
        )
        return Response(PostReportSerializer(report).data, status=201 if created else 200)


class SupportThreadView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SupportThreadSerializer

    def get_thread(self, request):
        user = request.user
        requested_user_id = request.query_params.get("user_id")
        is_support_operator = is_support_account(user)
        if requested_user_id:
            if not is_support_operator:
                raise PermissionDenied("Only the support account can select another user.")
            target = get_object_or_404(user.__class__, pk=requested_user_id)
        else:
            target = user
        support_user = user.__class__.objects.filter(username__iexact="support", is_active=True).first()
        defaults = {"assigned_to": support_user} if support_user and target != support_user else {}
        thread, _ = SupportThread.objects.get_or_create(user=target, defaults=defaults)
        return thread

    def get(self, request):
        return Response(SupportThreadSerializer(self.get_thread(request), context={"request": request}).data)


class SupportMessageListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SupportMessageSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_thread(self):
        helper = SupportThreadView()
        return helper.get_thread(self.request)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return SupportMessage.objects.none()
        return SupportMessage.objects.filter(
            thread=self.get_thread(), deleted_at__isnull=True
        ).select_related("sender").order_by("created_at", "id")

    def perform_create(self, serializer):
        thread = self.get_thread()
        key = self.request.headers.get("Idempotency-Key", "").strip()
        message, _ = create_support_message(serializer, thread, self.request.user, key)
        serializer.instance = message


def is_support_account(user):
    return bool(
        user and user.is_authenticated and (
            user.is_superuser
            or user.role == user.Role.SUPER_ADMIN
            or user.username.lower() == "support"
            or user.has_platform_permission(user.Permission.SUPPORT_MANAGE)
        )
    )


def create_support_message(serializer, thread, sender, idempotency_key=""):
    """Persist a support reply and its private notification/outbox as one unit."""
    if len(idempotency_key) > 120:
        raise ValidationError({"Idempotency-Key": "Must be at most 120 characters."})
    with transaction.atomic():
        thread = SupportThread.objects.select_for_update().select_related("user").get(pk=thread.pk)
        if idempotency_key:
            existing = SupportMessage.objects.filter(
                thread=thread, sender=sender, idempotency_key=idempotency_key,
            ).first()
            if existing:
                return existing, False
        message = serializer.save(
            thread=thread, sender=sender, delivered_at=timezone.now(),
            idempotency_key=idempotency_key,
        )
        update_support_thread_after_message(thread, sender, message)
        if is_support_account(sender) and sender.pk != thread.user_id:
            notification, created = Notification.objects.get_or_create(
                source_key=f"SUPPORT_REPLY:{message.pk}",
                defaults={
                    "recipient": thread.user,
                    "created_by": sender,
                    "title": "پاسخ پشتیبانی",
                    "message": "پاسخ سؤال شما در سوکانکس داده شد.",
                    "notification_type": Notification.Type.SYSTEM,
                    "action_label": "مشاهده پاسخ",
                    "target_url": "/chat/support",
                    "send_sms": True,
                },
            )
            if created:
                NotificationService.queue_sms(notification, allow_inline=False)
        return message, True


def update_support_thread_after_message(thread, sender, message):
    if is_support_account(sender) and sender.pk != thread.user_id:
        if thread.status == SupportThread.Status.PENDING:
            thread.status = SupportThread.Status.OPEN
    elif thread.status == SupportThread.Status.CLOSED:
        thread.status = SupportThread.Status.OPEN
        thread.closed_at = None
        thread.is_closed = False
    thread.last_message_at = message.created_at
    thread.save(update_fields=[
        "status", "closed_at", "is_closed", "last_message_at", "updated_at"
    ])


def support_thread_for(user, pk):
    queryset = SupportThread.objects.select_related("user", "assigned_to")
    thread = get_object_or_404(queryset, pk=pk)
    if not is_support_account(user) and thread.user_id != user.id:
        raise PermissionDenied("You cannot access another user's support conversation.")
    return thread


class SupportPagination(DefaultPagination):
    page_size = 30


class SupportConversationView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SupportThreadSerializer

    def get(self, request):
        if is_support_account(request.user):
            raise PermissionDenied("The support account must use the conversations inbox.")
        support_user = request.user.__class__.objects.filter(username="support", is_active=True).first()
        if not support_user:
            raise ValidationError("The support account is not configured. Run ensure_support_account.")
        thread, _ = SupportThread.objects.get_or_create(
            user=request.user,
            defaults={"assigned_to": support_user},
        )
        if thread.assigned_to_id != support_user.id:
            thread.assigned_to = support_user
            thread.save(update_fields=["assigned_to", "updated_at"])
        return Response(SupportThreadSerializer(thread, context={"request": request}).data)


class SupportConversationDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SupportThreadSerializer
    queryset = SupportThread.objects.select_related("user", "assigned_to")
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        return support_thread_for(self.request.user, self.kwargs["pk"])

    def get_serializer_class(self):
        return SupportThreadUpdateSerializer if self.request.method == "PATCH" else SupportThreadSerializer

    def patch(self, request, *args, **kwargs):
        if not is_support_account(request.user):
            raise PermissionDenied("Only the support account can update a ticket.")
        thread = self.get_object()
        serializer = SupportThreadUpdateSerializer(thread, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()
        if "status" in serializer.validated_data:
            closed = updated.status == SupportThread.Status.CLOSED
            updated.closed_at = timezone.now() if closed else None
            updated.is_closed = closed
            updated.save(update_fields=["closed_at", "is_closed", "updated_at"])
        return Response(SupportThreadSerializer(updated, context={"request": request}).data)


class SupportConversationMessageView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SupportMessageSerializer
    pagination_class = SupportPagination
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_throttles(self):
        return [SupportMessageRateThrottle()] if self.request.method == "POST" else []

    def get_thread(self):
        return support_thread_for(self.request.user, self.kwargs["pk"])

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return SupportMessage.objects.none()
        return SupportMessage.objects.filter(
            thread=self.get_thread(), deleted_at__isnull=True
        ).select_related("sender").order_by("created_at", "id")

    def perform_create(self, serializer):
        thread = self.get_thread()
        key = self.request.headers.get("Idempotency-Key", "").strip()
        message, created = create_support_message(serializer, thread, self.request.user, key)
        serializer.instance = message
        if not created:
            return
        payload = SupportMessageSerializer(message, context={"request": self.request}).data
        transaction.on_commit(lambda: async_to_sync(get_channel_layer().group_send)(
            f"support_{thread.pk}", {"type": "support.event", "payload": {"type": "message.created", "data": payload}}
        ))


class SupportConversationReadView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EmptySerializer

    def post(self, request, pk):
        thread = support_thread_for(request.user, pk)
        SupportMessage.objects.filter(
            thread=thread, is_read=False, deleted_at__isnull=True
        ).exclude(sender=request.user).update(is_read=True, read_at=timezone.now())
        return Response({"unread_count": 0})


class SupportQueueView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SupportThreadSerializer
    pagination_class = SupportPagination

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return SupportThread.objects.none()
        if not is_support_account(self.request.user):
            raise PermissionDenied("Only the support account can access the inbox.")
        queryset = SupportThread.objects.select_related("user", "assigned_to").annotate(
            unread_count_value=Count(
                "messages",
                filter=Q(messages__is_read=False) & ~Q(messages__sender=self.request.user),
            )
        ).prefetch_related(Prefetch(
            "messages",
            queryset=SupportMessage.objects.filter(deleted_at__isnull=True).select_related("sender").order_by("-created_at", "-id")[:1],
            to_attr="prefetched_latest_messages",
        ))
        status_value = self.request.query_params.get("status")
        if status_value:
            queryset = queryset.filter(status=status_value)
        search = self.request.query_params.get("search", "").strip()
        if search:
            query = (
                Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
                | Q(user__username__icontains=search)
                | Q(user__phone__icontains=search)
            )
            if search.isdigit():
                query |= Q(pk=int(search))
            queryset = queryset.filter(query)
        return queryset.order_by("-updated_at", "-id")


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
