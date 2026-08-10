from rest_framework import serializers

from common.validators import (
    validate_attachment_upload,
    validate_image_upload,
    validate_video_upload,
)

from .models import (
    ChatRoom, Message, PostComment, PostReaction, PostReport,
    SupportMessage, SupportThread, TraderPost, UserFollow,
)
from .services import ChatService


class ChatRoomSerializer(
    serializers.ModelSerializer
):

    member_count = serializers.IntegerField(
        read_only=True,
    )

    is_member = serializers.BooleanField(
        read_only=True,
    )

    class Meta:
        model = ChatRoom

        fields = (
            "id",
            "name",
            "slug",
            "description",
            "image",
            "is_public",
            "member_count",
            "is_member",
            "created_at",
        )


class ChatRoomWriteSerializer(
    serializers.ModelSerializer
):

    class Meta:
        model = ChatRoom

        fields = (
            "id",
            "name",
            "slug",
            "description",
            "image",
            "is_public",
            "is_active",
            "created_at",
            "updated_at",
        )

        read_only_fields = (
            "id",
            "slug",
            "created_at",
            "updated_at",
        )

    def validate_image(self, value):
        return validate_image_upload(
            value,
            max_size_mb=5,
            file_label="Room image",
        )


class MessageSerializer(
    serializers.ModelSerializer
):

    sender = serializers.CharField(
        source="sender.username",
        read_only=True,
        allow_null=True,
    )

    reply_to_text = serializers.CharField(
        source="reply_to.text",
        read_only=True,
        allow_null=True,
    )

    can_delete = serializers.SerializerMethodField()

    class Meta:
        model = Message

        fields = (
            "id",
            "sender",
            "text",
            "attachment",
            "reply_to",
            "reply_to_text",
            "is_deleted",
            "can_delete",
            "created_at",
            "updated_at",
        )

        read_only_fields = (
            "id",
            "sender",
            "is_deleted",
            "can_delete",
            "created_at",
            "updated_at",
        )

    def get_can_delete(self, obj):
        request = self.context.get("request")

        if (
            request is None
            or not request.user.is_authenticated
            or obj.is_deleted
        ):
            return False

        return ChatService.can_delete_message(
            obj,
            request.user,
        )

    def validate(self, attrs):
        if (
            not attrs.get("text")
            and not attrs.get("attachment")
        ):
            raise serializers.ValidationError(
                "A message must contain "
                "text or an attachment."
            )

        return attrs

    def validate_attachment(self, value):
        return validate_attachment_upload(
            value,
            max_size_mb=20,
            file_label="Chat attachment",
        )


class SocialUserSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(read_only=True)
    first_name = serializers.CharField(read_only=True)
    last_name = serializers.CharField(read_only=True)
    avatar = serializers.ImageField(read_only=True)
    access_level = serializers.IntegerField(read_only=True)


class SupportUserSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(read_only=True)
    first_name = serializers.CharField(read_only=True)
    last_name = serializers.CharField(read_only=True)
    phone = serializers.CharField(read_only=True, allow_null=True)
    avatar = serializers.ImageField(read_only=True, allow_null=True)


class PostCommentSerializer(serializers.ModelSerializer):
    author = SocialUserSerializer(read_only=True)

    class Meta:
        model = PostComment
        fields = ("id", "post", "author", "parent", "text", "is_edited", "created_at", "updated_at")
        read_only_fields = ("id", "post", "author", "is_edited", "created_at", "updated_at")


class TraderPostSerializer(serializers.ModelSerializer):
    author = SocialUserSerializer(read_only=True)
    reactions_count = serializers.IntegerField(read_only=True)
    comments_count = serializers.IntegerField(read_only=True)
    is_reacted = serializers.BooleanField(read_only=True)
    is_saved = serializers.BooleanField(read_only=True)

    class Meta:
        model = TraderPost
        fields = (
            "id", "author", "text", "image", "video", "visibility",
            "is_edited", "reactions_count", "comments_count", "is_reacted",
            "is_saved", "created_at", "updated_at",
        )
        read_only_fields = (
            "id", "author", "is_edited", "reactions_count", "comments_count",
            "is_reacted", "is_saved", "created_at", "updated_at",
        )

    def validate_image(self, value):
        return validate_image_upload(value, max_size_mb=10, file_label="Post image")

    def validate_video(self, value):
        return validate_video_upload(value, max_size_mb=200, file_label="Post video")

    def validate(self, attrs):
        text = attrs.get("text", getattr(self.instance, "text", ""))
        image = attrs.get("image", getattr(self.instance, "image", None))
        video = attrs.get("video", getattr(self.instance, "video", None))
        if not text and not image and not video:
            raise serializers.ValidationError("A post must contain text, image, or video.")
        return attrs


class PostReactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PostReaction
        fields = ("reaction_type",)


class PostReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = PostReport
        fields = ("id", "post", "reason", "status", "created_at")
        read_only_fields = ("id", "post", "status", "created_at")


class FollowSerializer(serializers.ModelSerializer):
    following = SocialUserSerializer(read_only=True)

    class Meta:
        model = UserFollow
        fields = ("id", "following", "created_at")
        read_only_fields = fields


class SupportThreadSerializer(serializers.ModelSerializer):
    slug = serializers.CharField(read_only=True)
    user = SupportUserSerializer(read_only=True)
    assigned_to = SupportUserSerializer(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    unread_count = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()

    class Meta:
        model = SupportThread
        fields = ("id", "slug", "user", "assigned_to", "status", "status_display", "priority", "subject", "unread_count", "last_message", "last_message_at", "created_at", "updated_at", "closed_at")
        read_only_fields = fields

    def get_unread_count(self, obj) -> int:
        request = self.context.get("request")
        if not request:
            return 0
        annotated = getattr(obj, "unread_count_value", None)
        if annotated is not None:
            return annotated
        return obj.messages.filter(is_read=False).exclude(sender=request.user).count()

    def get_last_message(self, obj) -> dict | None:
        messages = getattr(obj, "prefetched_latest_messages", None)
        message = messages[0] if messages else obj.messages.order_by("-created_at", "-id").first()
        if not message:
            return None
        return {"id": message.id, "text": message.text, "created_at": message.created_at}


class SupportThreadUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportThread
        fields = ("status", "priority", "subject")


class SupportMessageSerializer(serializers.ModelSerializer):
    sender = SupportUserSerializer(read_only=True)
    sender_username = serializers.CharField(source="sender.username", read_only=True)
    is_mine = serializers.SerializerMethodField()

    class Meta:
        model = SupportMessage
        fields = ("id", "sender", "sender_username", "text", "attachment", "is_mine", "is_read", "created_at", "updated_at", "delivered_at", "read_at")
        read_only_fields = ("id", "sender", "sender_username", "is_mine", "is_read", "created_at", "updated_at", "delivered_at", "read_at")

    def get_is_mine(self, obj) -> bool:
        request = self.context.get("request")
        return bool(request and obj.sender_id == request.user.id)

    def validate_attachment(self, value):
        return validate_attachment_upload(value, max_size_mb=20, file_label="Support attachment")

    def validate_text(self, value):
        from django.utils.html import strip_tags
        return strip_tags(value).strip()

    def validate(self, attrs):
        if not attrs.get("text") and not attrs.get("attachment"):
            raise serializers.ValidationError("A support message needs text or an attachment.")
        return attrs
