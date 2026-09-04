from django.utils import timezone
from django.conf import settings
from datetime import timedelta

from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from .models import LiveChatMessage, LiveEvent, LivePresence, SpeakRequest

from common.validators import (
    validate_image_upload,
)
from common.content_access import AllowedLevelsSerializerMixin


class LiveEventListSerializer(
    AllowedLevelsSerializerMixin,
    serializers.ModelSerializer
):

    host = serializers.CharField(
        source="host.username",
        read_only=True,
        allow_null=True,
    )

    is_live_now = (
        serializers.SerializerMethodField()
    )
    status = serializers.SerializerMethodField()
    status_message = serializers.SerializerMethodField()
    can_join = serializers.SerializerMethodField()
    join_opens_at = serializers.SerializerMethodField()
    join_url = serializers.SerializerMethodField()
    replay_url = serializers.SerializerMethodField()

    class Meta:
        model = LiveEvent

        fields = (
            "id",
            "title",
            "slug",
            "thumbnail",
            "starts_at",
            "ends_at",
            "status",
            "viewer_count",
            "allowed_levels",
            "host",
            "is_live_now",
            "status_message",
            "can_join",
            "join_opens_at",
            "join_url",
            "replay_url",
        )

    def get_is_live_now(self, obj) -> bool:
        now = timezone.now()

        return (
            self.get_status(obj) == LiveEvent.Status.LIVE
            and obj.starts_at <= now
            and (
                obj.ends_at is None
                or obj.ends_at >= now
            )
        )

    def get_status(self, obj) -> str:
        if not obj.is_active:
            return LiveEvent.Status.DISABLED
        if obj.status in (LiveEvent.Status.CANCELLED, LiveEvent.Status.DISABLED):
            return obj.status
        now = timezone.now()
        if now < obj.starts_at:
            return LiveEvent.Status.SCHEDULED
        if obj.ends_at and now > obj.ends_at:
            return LiveEvent.Status.ENDED
        return LiveEvent.Status.LIVE

    def get_status_message(self, obj) -> str:
        status_value = self.get_status(obj)
        if status_value == LiveEvent.Status.LIVE:
            return "لایو در حال انجام است"
        if status_value == LiveEvent.Status.SCHEDULED:
            return "لایو هنوز شروع نشده است"
        if status_value == LiveEvent.Status.ENDED:
            return "لایو به پایان رسیده است"
        return "این رویداد در دسترس نیست"

    @extend_schema_field(serializers.DateTimeField())
    def get_join_opens_at(self, obj):
        return obj.starts_at - timedelta(minutes=obj.join_early_minutes)

    def get_can_join(self, obj) -> bool:
        now = timezone.now()
        if not obj.is_active or obj.status in (LiveEvent.Status.CANCELLED, LiveEvent.Status.DISABLED, LiveEvent.Status.ENDED):
            return False
        if now < self.get_join_opens_at(obj):
            return False
        return obj.ends_at is None or now <= obj.ends_at

    def get_join_url(self, obj) -> str:
        if not self.get_can_join(obj):
            return ""
        return obj.external_url or obj.provider_join_url or obj.stream_url

    def get_replay_url(self, obj) -> str:
        return obj.replay_url if self.get_status(obj) == LiveEvent.Status.ENDED else ""


class LiveEventDetailSerializer(
    LiveEventListSerializer
):

    class Meta(
        LiveEventListSerializer.Meta
    ):

        fields = (
            LiveEventListSerializer.Meta.fields
            + (
                "description",
                "external_url",
                "ended_at",
                "created_at",
                "updated_at",
            )
        )

    external_url = serializers.SerializerMethodField()

    def get_external_url(self, obj) -> str:
        return self.get_join_url(obj)

class LiveEventWriteSerializer(
    AllowedLevelsSerializerMixin,
    serializers.ModelSerializer
):

    class Meta:
        model = LiveEvent

        fields = (
            "id",
            "title",
            "slug",
            "description",
            "thumbnail",
            "stream_url",
            "external_url",
            "join_early_minutes",
            "provider_join_url",
            "ended_at",
            "replay_url",
            "starts_at",
            "ends_at",
            "status",
            "host",
            "is_active",
            "allowed_levels",
            "created_at",
            "updated_at",
        )

        read_only_fields = (
            "id",
            "slug",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs):
        starts_at = attrs.get(
            "starts_at",
            getattr(
                self.instance,
                "starts_at",
                None,
            ),
        )

        ends_at = attrs.get(
            "ends_at",
            getattr(
                self.instance,
                "ends_at",
                None,
            ),
        )

        status_value = attrs.get(
            "status",
            getattr(
                self.instance,
                "status",
                LiveEvent.Status.SCHEDULED,
            ),
        )

        stream_url = attrs.get(
            "stream_url",
            getattr(
                self.instance,
                "stream_url",
                "",
            ),
        )
        external_url = attrs.get("external_url", getattr(self.instance, "external_url", ""))
        provider_join_url = attrs.get(
            "provider_join_url", getattr(self.instance, "provider_join_url", "")
        )

        if (
            starts_at
            and ends_at
            and ends_at <= starts_at
        ):
            raise serializers.ValidationError(
                {
                    "ends_at": (
                        "End time must be after "
                        "start time."
                    )
                }
            )

        if (
            status_value == LiveEvent.Status.LIVE
            and not (stream_url or external_url or provider_join_url)
        ):
            raise serializers.ValidationError(
                {
                    "stream_url": (
                        "برای رویداد در حال پخش، وارد کردن لینک لایو الزامی است."
                    )
                }
            )

        return attrs

    def create(self, validated_data):
        validated_data.setdefault("join_early_minutes", settings.LIVE_JOIN_EARLY_MINUTES)
        return super().create(validated_data)

    def validate_join_early_minutes(self, value):
        if value > 1440:
            raise serializers.ValidationError("زمان ورود زودتر نمی‌تواند بیشتر از ۱۴۴۰ دقیقه باشد.")
        return value

    def validate_thumbnail(self, value):
        return validate_image_upload(
            value,
            max_size_mb=8,
            file_label="Live event thumbnail",
        )


class LivePresenceSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = LivePresence
        fields = ("id", "user", "username", "joined_at", "last_seen_at", "is_muted")
        read_only_fields = fields


class SpeakRequestSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = SpeakRequest
        fields = ("id", "user", "username", "message", "status", "created_at", "reviewed_at")
        read_only_fields = ("id", "user", "username", "status", "created_at", "reviewed_at")


class SpeakRequestReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = SpeakRequest
        fields = ("status",)


class LiveChatMessageSerializer(serializers.ModelSerializer):
    sender = serializers.CharField(source="sender.username", read_only=True)

    class Meta:
        model = LiveChatMessage
        fields = ("id", "sender", "text", "created_at")
        read_only_fields = ("id", "sender", "created_at")

    def validate_text(self, value):
        from django.utils.html import strip_tags
        value = strip_tags(value).strip()
        if not value:
            raise serializers.ValidationError("Message cannot be empty.")
        return value
