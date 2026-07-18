from rest_framework import serializers

from .models import Broker


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
        if value and value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError(
                "Broker logo size cannot exceed 5 MB."
            )

        return value

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