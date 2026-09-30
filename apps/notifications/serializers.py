from django.db.models import Count
from rest_framework import serializers

from apps.accounts.models import User
from common.content_access import AllowedLevelsSerializerMixin

from .models import Notification
from .models import WebPushSubscription


class NotificationSerializer(AllowedLevelsSerializerMixin,
    serializers.ModelSerializer
):

    is_read = serializers.SerializerMethodField()

    created_by = serializers.CharField(
        source="created_by.username",
        read_only=True,
        allow_null=True,
    )
    sms_summary = serializers.SerializerMethodField()

    class Meta:
        model = Notification

        fields = (
            "id",
            "title",
            "message",
            "notification_type",
            "priority",
            "action_label",
            "allowed_levels",
            "send_sms",
            "sms_summary",
            "image",
            "expires_at",
            "recipient",
            "target_role",
            "target_url",
            "created_by",
            "is_read",
            "is_active",
            "created_at",
            "updated_at",
        )

        read_only_fields = (
            "id",
            "created_by",
            "is_read",
            "created_at",
            "updated_at",
            "sms_summary",
        )

    def get_sms_summary(self, obj) -> dict:
        annotated = all(
            hasattr(obj, field)
            for field in ("sms_total", "sms_sent", "sms_failed", "sms_pending")
        )
        if annotated:
            return {
                "total": obj.sms_total,
                "sent": obj.sms_sent,
                "failed": obj.sms_failed,
                "pending": obj.sms_pending,
            }
        counts = {"SENT": 0, "FAILED": 0, "PENDING": 0}
        for row in obj.sms_deliveries.values("status").annotate(total=Count("id")):
            counts[row["status"]] = row["total"]
        return {
            "total": sum(counts.values()),
            "sent": counts["SENT"],
            "failed": counts["FAILED"],
            "pending": counts["PENDING"],
        }

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
        instance = self.instance
        recipient = attrs.get(
            "recipient",
            getattr(instance, "recipient", None),
        )
        target_role = attrs.get(
            "target_role",
            getattr(instance, "target_role", ""),
        )
        allowed_levels = attrs.get("allowed_levels")
        if (
            recipient
            and target_role
        ):
            raise serializers.ValidationError(
                (
                    "Choose either a recipient or "
                    "a target role, not both."
                )
            )
        if recipient and allowed_levels is not None:
            raise serializers.ValidationError(
                "Choose either a recipient or access levels, not both."
            )
        if target_role and allowed_levels is not None:
            raise serializers.ValidationError(
                "Choose either a target role or access levels, not both."
            )

        return attrs


class WebPushKeysSerializer(serializers.Serializer):
    p256dh = serializers.RegexField(r"^[A-Za-z0-9_-]{20,256}$")
    auth = serializers.RegexField(r"^[A-Za-z0-9_-]{8,128}$")


class WebPushSubscriptionCreateSerializer(serializers.Serializer):
    endpoint = serializers.URLField(max_length=2048)
    keys = WebPushKeysSerializer()

    def validate_endpoint(self, value):
        from urllib.parse import urlsplit

        host = (urlsplit(value).hostname or "").lower().rstrip(".")
        supported = (
            "fcm.googleapis.com",
            "push.services.mozilla.com",
            "push.apple.com",
            "notify.windows.com",
            "wns.windows.com",
        )
        if not value.startswith("https://") or not any(
            host == domain or host.endswith("." + domain) for domain in supported
        ):
            raise serializers.ValidationError("Push endpoint provider is not supported.")
        return value


class WebPushSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebPushSubscription
        fields = ("id", "created_at", "last_seen_at", "is_active")
        read_only_fields = fields
