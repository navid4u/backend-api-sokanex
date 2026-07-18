from rest_framework import serializers

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
            "source_type",
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
                "video_file",
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
            "source_type",
            "video_file",
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
            "video_file": {
                "required": False,
                "allow_null": True,
            },
            "external_url": {
                "required": False,
                "allow_blank": True,
            },
        }

    def validate(self, attrs):
        source_type = attrs.get(
            "source_type",
            getattr(
                self.instance,
                "source_type",
                None,
            ),
        )

        video_file = attrs.get(
            "video_file",
            getattr(
                self.instance,
                "video_file",
                None,
            ),
        )

        external_url = attrs.get(
            "external_url",
            getattr(
                self.instance,
                "external_url",
                "",
            ),
        )

        if (
            source_type == Video.SourceType.UPLOAD
            and not video_file
        ):
            raise serializers.ValidationError(
                {
                    "video_file": (
                        "A video file is required "
                        "for uploaded videos."
                    )
                }
            )

        if (
            source_type == Video.SourceType.UPLOAD
            and external_url
        ):
            raise serializers.ValidationError(
                {
                    "external_url": (
                        "External URL must be empty "
                        "for uploaded videos."
                    )
                }
            )

        if (
            source_type == Video.SourceType.EXTERNAL
            and not external_url
        ):
            raise serializers.ValidationError(
                {
                    "external_url": (
                        "An external URL is required "
                        "for external videos."
                    )
                }
            )

        if (
            source_type == Video.SourceType.EXTERNAL
            and video_file
        ):
            raise serializers.ValidationError(
                {
                    "video_file": (
                        "Video file must be empty "
                        "for external videos."
                    )
                }
            )

        return attrs

    def validate_thumbnail(self, value):
        if value and value.size > 8 * 1024 * 1024:
            raise serializers.ValidationError(
                "Thumbnail size cannot exceed 8 MB."
            )

        return value

    def validate_video_file(self, value):
        if value and value.size > 500 * 1024 * 1024:
            raise serializers.ValidationError(
                "Video file size cannot exceed 500 MB."
            )

        return value