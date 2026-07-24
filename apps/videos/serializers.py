from rest_framework import serializers

from common.validators import validate_image_upload

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
            "thumbnail",
            "duration_seconds",
            "category",
            "author",
            "status",
            "published_at",
            "created_at",
        )


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
            "thumbnail",
            "duration_seconds",
            "category",
            "status",
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
        )

        extra_kwargs = {
            "external_url": {
                "required": True,
                "allow_blank": False,
            },
        }

    def validate_external_url(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "Video URL is required."
            )

        return value

    def validate_thumbnail(self, value):
        return validate_image_upload(
            value,
            max_size_mb=8,
            file_label="Video thumbnail",
        )