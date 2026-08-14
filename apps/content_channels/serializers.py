from rest_framework import serializers

from django.conf import settings
from django.utils import timezone

from common.validators import validate_audio_upload, validate_image_upload, validate_video_upload
from .models import ChannelPost


class ChannelPostSerializer(serializers.ModelSerializer):
    channel = serializers.CharField(source="channel.slug", read_only=True)
    author = serializers.CharField(source="author.username", read_only=True)
    author_name = serializers.SerializerMethodField()
    signal_status = serializers.CharField(source="signal.status", read_only=True, allow_null=True)
    signal_status_display = serializers.CharField(source="signal.get_status_display", read_only=True, allow_null=True)
    scope_display = serializers.CharField(source="get_scope_display", read_only=True)

    class Meta:
        model = ChannelPost
        fields = (
            "id", "channel", "title", "body", "image", "video", "audio", "cover",
            "author", "author_name", "published_at", "is_pinned", "signal",
            "signal_status", "signal_status_display", "scope", "scope_display", "created_at", "updated_at",
        )
        read_only_fields = ("id", "channel", "author", "author_name", "created_at", "updated_at")

    def get_author_name(self, obj) -> str:
        return obj.author.get_full_name().strip() or obj.author.username

    def validate_image(self, value):
        return validate_image_upload(value, max_size_mb=10, file_label="Channel image")

    def validate_cover(self, value):
        return validate_image_upload(value, max_size_mb=10, file_label="Channel cover")

    def validate_video(self, value):
        return validate_video_upload(value, max_size_mb=1024, file_label="Channel video")

    def validate_audio(self, value):
        allowed = {"audio/mpeg", "audio/mp4", "audio/wav", "audio/ogg", "audio/webm"}
        if getattr(value, "content_type", "").split(";", 1)[0].lower() not in allowed:
            raise serializers.ValidationError("Unsupported audio content type.")
        if value.size > 50 * 1024 * 1024:
            raise serializers.ValidationError("Audio cannot exceed 50 MB.")
        return value

    def validate(self, attrs):
        channel = self.context.get("channel") or getattr(self.instance, "channel", None)
        if channel and channel.slug == "internal-analysis" and not attrs.get("scope", getattr(self.instance, "scope", "")):
            raise serializers.ValidationError({"scope": "Scope is required for internal analysis."})
        return attrs


class InternalAnalysisPostSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()
    scope_display = serializers.CharField(source="get_scope_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = ChannelPost
        fields = (
            "id", "title", "body", "scope", "scope_display", "status",
            "status_display", "image", "video", "audio", "cover", "is_pinned",
            "author", "author_name", "published_at", "views_count", "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "author", "author_name", "views_count", "created_at", "updated_at")

    def get_author_name(self, obj) -> str:
        return obj.author.get_full_name().strip() or obj.author.username

    def validate_image(self, value):
        return validate_image_upload(value, max_size_mb=settings.MEDIA_MAX_IMAGE_MB, file_label="Analysis image")

    def validate_cover(self, value):
        return validate_image_upload(value, max_size_mb=settings.MEDIA_MAX_IMAGE_MB, file_label="Analysis cover")

    def validate_video(self, value):
        return validate_video_upload(value, max_size_mb=settings.MEDIA_MAX_VIDEO_MB, file_label="Analysis video")

    def validate_audio(self, value):
        return validate_audio_upload(value, max_size_mb=settings.MEDIA_MAX_AUDIO_MB, file_label="Analysis audio")

    def validate(self, attrs):
        status_value = attrs.get("status", getattr(self.instance, "status", ChannelPost.Status.PUBLISHED))
        published_at = attrs.get("published_at", getattr(self.instance, "published_at", None))
        if status_value == ChannelPost.Status.SCHEDULED:
            if not published_at:
                raise serializers.ValidationError({"published_at": "Scheduled posts require a publish time."})
            if published_at <= timezone.now():
                raise serializers.ValidationError({"published_at": "Scheduled publish time must be in the future."})
        if status_value == ChannelPost.Status.PUBLISHED and not published_at:
            attrs["published_at"] = timezone.now()
        return attrs
