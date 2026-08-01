from rest_framework import serializers

from common.validators import validate_image_upload, validate_video_upload
from common.content_access import AllowedLevelsSerializerMixin

from .models import Video, VideoCategory


class VideoCategorySerializer(
    serializers.ModelSerializer
):

    class Meta:
        model = VideoCategory

        fields = (
            "id",
            "name",
            "slug",
        )

        read_only_fields = (
            "id",
            "slug",
        )


class VideoListSerializer(
    AllowedLevelsSerializerMixin,
    serializers.ModelSerializer
):

    author = serializers.CharField(
        source="author.username",
        read_only=True,
    )

    category = VideoCategorySerializer(
        read_only=True,
    )

    class Meta:
        model = Video

        fields = (
            "id",
            "title",
            "slug",
            "summary",
            "external_url",
            "video_file",
            "thumbnail",
            "duration_seconds",
            "original_filename",
            "mime_type",
            "file_size_bytes",
            "width",
            "height",
            "category",
            "author",
            "status",
            "allowed_levels",
            "published_at",
            "created_at",
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not instance.video_file:
            for field in (
                "video_file", "original_filename", "mime_type",
                "file_size_bytes", "width", "height",
            ):
                data.pop(field, None)
        return data


class VideoDetailSerializer(
    VideoListSerializer
):

    class Meta(VideoListSerializer.Meta):

        fields = (
            VideoListSerializer.Meta.fields
            + (
                "updated_at",
            )
        )


class VideoWriteSerializer(
    AllowedLevelsSerializerMixin,
    serializers.ModelSerializer
):

    class Meta:
        model = Video

        fields = (
            "id",
            "title",
            "slug",
            "summary",
            "external_url",
            "video_file",
            "thumbnail",
            "duration_seconds",
            "original_filename",
            "mime_type",
            "file_size_bytes",
            "width",
            "height",
            "category",
            "status",
            "allowed_levels",
            "published_at",
            "created_at",
            "updated_at",
        )

        read_only_fields = (
            "id",
            "slug",
            "published_at",
            "created_at",
            "updated_at",
            "original_filename",
            "mime_type",
            "file_size_bytes",
        )

        extra_kwargs = {
            "external_url": {"required": False, "allow_blank": True},
            "video_file": {"required": False, "allow_null": True},
        }

    def validate_external_url(self, value):
        value = value.strip()

        return value

    def validate_video_file(self, value):
        return validate_video_upload(value, max_size_mb=500, file_label="Video file")

    def validate(self, attrs):
        instance = self.instance
        external_url = attrs.get("external_url", getattr(instance, "external_url", ""))
        video_file = attrs.get("video_file", getattr(instance, "video_file", None))
        if not external_url and not video_file:
            raise serializers.ValidationError(
                {"external_url": "Upload a video file or provide external_url."}
            )
        if external_url and video_file:
            raise serializers.ValidationError(
                "Use either video_file or external_url, not both."
            )
        uploaded = attrs.get("video_file")
        if uploaded:
            attrs["original_filename"] = uploaded.name[:255]
            attrs["mime_type"] = getattr(uploaded, "content_type", "")[:100]
            attrs["file_size_bytes"] = uploaded.size
        return attrs

    def validate_thumbnail(self, value):
        return validate_image_upload(
            value,
            max_size_mb=8,
            file_label="Video thumbnail",
        )
