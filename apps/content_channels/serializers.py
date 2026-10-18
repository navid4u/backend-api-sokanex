from rest_framework import serializers

from django.conf import settings
from django.utils import timezone
from django.utils.html import strip_tags
from urllib.parse import urlparse

from common.validators import (
    validate_audio_upload,
    validate_image_upload,
    validate_uploaded_file,
    validate_video_upload,
)
from .models import ChannelPost
from apps.accounts.models import User
from apps.videos.models import Video


class OptionalVideoIdField(serializers.IntegerField):
    def to_internal_value(self, data):
        if data is None or data == "" or data == "null":
            return None
        return super().to_internal_value(data)


class UsageGuideReferenceMixin:
    def _validate_usage_guide_reference(self, attrs):
        if "usage_guide_video_id" not in attrs:
            if attrs.get("usage_guide_video"):
                attrs["usage_guide_video_reference"] = None
            return attrs
        video_id = attrs.pop("usage_guide_video_id")
        if video_id is not None and attrs.get("usage_guide_video"):
            raise serializers.ValidationError({
                "usage_guide_video_id": "Select a library video or upload a file, not both."
            })
        if video_id is None:
            attrs["usage_guide_video_reference"] = None
            return attrs
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated or not (
            user.is_superuser or user.role == User.Role.SUPER_ADMIN
            or user.has_platform_permission(User.Permission.CONTENT_MANAGE)
            or user.has_platform_permission(User.Permission.INTERNAL_ANALYSIS_MANAGE)
        ):
            raise serializers.ValidationError({"usage_guide_video_id": "Video library access is required."})
        video = Video.objects.filter(
            pk=video_id, status=Video.Status.PUBLISHED,
            published_at__lte=timezone.now(),
        ).first()
        if not video or not (video.video_file or video.external_url):
            raise serializers.ValidationError({"usage_guide_video_id": "Selectable video not found."})
        attrs["usage_guide_video_reference"] = video
        attrs["usage_guide_video"] = None
        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        video = instance.usage_guide_video_reference
        data["usage_guide_video_id"] = video.pk if video else None
        if video:
            if video.video_file:
                request = self.context.get("request")
                url = video.video_file.url
                data["usage_guide_video"] = request.build_absolute_uri(url) if request else url
            else:
                data["usage_guide_video"] = video.external_url or None
        return data


class ChannelPostSerializer(UsageGuideReferenceMixin, serializers.ModelSerializer):
    usage_guide_video_id = OptionalVideoIdField(required=False, allow_null=True, min_value=1, write_only=True)
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
            "external_url", "more_info_text", "more_info_video",
            "usage_guide_text", "usage_guide_video", "usage_guide_video_id",
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

    def validate_external_url(self, value):
        value = value.strip()
        if value and urlparse(value).scheme.lower() not in {"http", "https"}:
            raise serializers.ValidationError("لینک فقط باید با http یا https شروع شود.")
        return value

    def validate_more_info_text(self, value):
        return strip_tags(value).replace("\x00", "").strip()

    def validate_usage_guide_text(self, value):
        return strip_tags(value).replace("\x00", "").strip()

    def _validate_detail_video(self, value, label):
        if value is None:
            return value
        try:
            return validate_uploaded_file(
                value,
                max_size=settings.INTERNAL_ANALYSIS_DETAIL_VIDEO_MAX_MB * 1024 * 1024,
                allowed_extensions={".mp4", ".webm", ".mov"},
                allowed_content_types={"video/mp4", "video/webm", "video/quicktime"},
                file_label=label,
            )
        except serializers.ValidationError as exc:
            raise serializers.ValidationError(
                f"{label} باید MP4، WebM یا QuickTime و حداکثر "
                f"{settings.INTERNAL_ANALYSIS_DETAIL_VIDEO_MAX_MB} مگابایت باشد."
            ) from exc

    def validate_more_info_video(self, value):
        return self._validate_detail_video(value, "ویدئوی معرفی بیشتر")

    def validate_usage_guide_video(self, value):
        return self._validate_detail_video(value, "ویدئوی راهنمای استفاده")

    def validate(self, attrs):
        channel = self.context.get("channel") or getattr(self.instance, "channel", None)
        if channel and channel.slug == "internal-analysis" and not attrs.get("scope", getattr(self.instance, "scope", "")):
            raise serializers.ValidationError({"scope": "Scope is required for internal analysis."})
        return self._validate_usage_guide_reference(attrs)


class InternalAnalysisPostSerializer(UsageGuideReferenceMixin, serializers.ModelSerializer):
    usage_guide_video_id = OptionalVideoIdField(required=False, allow_null=True, min_value=1, write_only=True)
    author_name = serializers.SerializerMethodField()
    scope_display = serializers.CharField(source="get_scope_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = ChannelPost
        fields = (
            "id", "title", "body", "scope", "scope_display", "status",
            "status_display", "image", "video", "audio", "cover", "is_pinned",
            "author", "author_name", "published_at", "views_count", "created_at",
            "updated_at", "source", "external_id",
            "external_url", "more_info_text", "more_info_video",
            "usage_guide_text", "usage_guide_video", "usage_guide_video_id",
        )
        read_only_fields = ("id", "author", "author_name", "views_count", "created_at", "updated_at", "source", "external_id")

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

    def validate_external_url(self, value):
        value = value.strip()
        if value and urlparse(value).scheme.lower() not in {"http", "https"}:
            raise serializers.ValidationError("لینک فقط باید با http یا https شروع شود.")
        return value

    def validate_more_info_text(self, value):
        return strip_tags(value).replace("\x00", "").strip()

    def validate_usage_guide_text(self, value):
        return strip_tags(value).replace("\x00", "").strip()

    def _validate_detail_video(self, value, label):
        if value is None:
            return value
        try:
            return validate_uploaded_file(
                value,
                max_size=settings.INTERNAL_ANALYSIS_DETAIL_VIDEO_MAX_MB * 1024 * 1024,
                allowed_extensions={".mp4", ".webm", ".mov"},
                allowed_content_types={"video/mp4", "video/webm", "video/quicktime"},
                file_label=label,
            )
        except serializers.ValidationError as exc:
            raise serializers.ValidationError(
                f"{label} باید MP4، WebM یا QuickTime و حداکثر "
                f"{settings.INTERNAL_ANALYSIS_DETAIL_VIDEO_MAX_MB} مگابایت باشد."
            ) from exc

    def validate_more_info_video(self, value):
        return self._validate_detail_video(value, "ویدئوی معرفی بیشتر")

    def validate_usage_guide_video(self, value):
        return self._validate_detail_video(value, "ویدئوی راهنمای استفاده")

    def validate(self, attrs):
        attrs = self._validate_usage_guide_reference(attrs)
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


class InternalAnalysisIngestionSerializer(serializers.Serializer):
    external_id = serializers.CharField(max_length=150, required=False, allow_blank=False)
    scope = serializers.ChoiceField(choices=ChannelPost.Scope.choices)
    title = serializers.CharField(max_length=250, allow_blank=False, trim_whitespace=True)
    body = serializers.CharField(allow_blank=False, trim_whitespace=True, max_length=20000)
    image = serializers.ImageField(required=False, allow_null=True)
    video = serializers.FileField(required=False, allow_null=True)
    audio = serializers.FileField(required=False, allow_null=True)

    def validate_image(self, value):
        return validate_image_upload(value, max_size_mb=settings.MEDIA_MAX_IMAGE_MB, file_label="Analysis image")

    def validate_video(self, value):
        return validate_video_upload(value, max_size_mb=settings.MEDIA_MAX_VIDEO_MB, file_label="Analysis video")

    def validate_audio(self, value):
        return validate_audio_upload(value, max_size_mb=settings.MEDIA_MAX_AUDIO_MB, file_label="Analysis audio")
