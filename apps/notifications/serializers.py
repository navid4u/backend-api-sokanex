from rest_framework import serializers

from apps.accounts.models import User

from .models import Notification


class NotificationSerializer(
    serializers.ModelSerializer
):

    is_read = serializers.SerializerMethodField()

    created_by = serializers.CharField(
        source="created_by.username",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = Notification

        fields = (
            "id",
            "title",
            "message",
            "notification_type",
            "recipient",
            "target_role",
            "target_url",
            "created_by",
            "is_read",
            "created_at",
        )

        read_only_fields = (
            "id",
            "created_by",
            "is_read",
            "created_at",
        )

    def validate_target_role(self, value):
        if (
            value
            and value not in User.Role.values
        ):
            raise serializers.ValidationError(
                "Invalid target role."
            )

        return value

    def get_is_read(self, obj) -> bool:
        return getattr(
            obj,
            "is_read",
            False,
        )

    def validate(self, attrs):
        if (
            attrs.get("recipient")
            and attrs.get("target_role")
        ):
            raise serializers.ValidationError(
                (
                    "Choose either a recipient or "
                    "a target role, not both."
                )
            )

        return attrs