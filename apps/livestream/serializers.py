from django.utils import timezone

from rest_framework import serializers

from .models import LiveEvent

from common.validators import (
    validate_image_upload,
)


class LiveEventListSerializer(
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
            "host",
            "is_live_now",
        )

    def get_is_live_now(self, obj) -> bool:
        now = timezone.now()

        return (
            obj.status == LiveEvent.Status.LIVE
            and obj.starts_at <= now
            and (
                obj.ends_at is None
                or obj.ends_at >= now
            )
        )


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
                "stream_url",
                "replay_url",
                "created_at",
                "updated_at",
            )
        )


class LiveEventWriteSerializer(
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
            "replay_url",
            "starts_at",
            "ends_at",
            "status",
            "host",
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
            and not stream_url
        ):
            raise serializers.ValidationError(
                {
                    "stream_url": (
                        "Stream URL is required "
                        "for a live event."
                    )
                }
            )

        return attrs

    def validate_thumbnail(self, value):
        return validate_image_upload(
            value,
            max_size_mb=8,
            file_label="Live event thumbnail",
        )