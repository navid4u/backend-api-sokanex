from rest_framework import serializers

from .models import Broker

from common.validators import (
    validate_image_upload,
)

class BrokerListSerializer(
    serializers.ModelSerializer
):

    class Meta:
        model = Broker

        fields = (
            "id",
            "name",
            "slug",
            "short_description",
            "logo",
            "country",
            "regulation",
            "minimum_deposit",
            "rating",
            "features",
            "sort_order",
            "is_active",
        )


class BrokerDetailSerializer(
    BrokerListSerializer
):

    class Meta(BrokerListSerializer.Meta):

        fields = (
            BrokerListSerializer.Meta.fields
            + (
                "description",
                "website_url",
                "registration_url",
                "support_url",
                "updated_at",
            )
        )


class BrokerWriteSerializer(
    serializers.ModelSerializer
):

    class Meta:
        model = Broker

        fields = (
            "id",
            "name",
            "slug",
            "short_description",
            "description",
            "logo",
            "website_url",
            "registration_url",
            "support_url",
            "country",
            "regulation",
            "minimum_deposit",
            "rating",
            "features",
            "is_active",
            "sort_order",
            "created_at",
            "updated_at",
        )

        read_only_fields = (
            "id",
            "slug",
            "created_at",
            "updated_at",
        )

    def validate_logo(self, value):
        return validate_image_upload(
            value,
            max_size_mb=5,
            file_label="Broker logo",
        )

    def validate_features(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError(
                "Features must be a list."
            )

        if not all(
            isinstance(item, str)
            for item in value
        ):
            raise serializers.ValidationError(
                "Every feature must be a string."
            )

        return value