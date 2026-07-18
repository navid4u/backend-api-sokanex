from rest_framework import serializers

from .models import ChatRoom, Message


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
        if value and value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError(
                "Room image size cannot exceed 5 MB."
            )

        return value


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
        if value and value.size > 20 * 1024 * 1024:
            raise serializers.ValidationError(
                "Attachment size cannot exceed 20 MB."
            )

        return value