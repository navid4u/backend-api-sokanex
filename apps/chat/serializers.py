from rest_framework import serializers

from .models import ChatRoom, Message

from common.validators import (
    validate_attachment_upload,
    validate_image_upload,
)

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
            "created_at",
            "updated_at",
        )

        read_only_fields = (
            "id",
            "sender",
            "is_deleted",
            "created_at",
            "updated_at",
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