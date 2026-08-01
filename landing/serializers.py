from rest_framework import serializers

from common.validators import validate_image_upload

from .models import LandingPage, LandingSection


class JSONObjectField(serializers.JSONField):
    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        if not isinstance(value, dict):
            raise serializers.ValidationError("Must be a JSON object.")
        return value


class LandingSectionSerializer(serializers.ModelSerializer):
    content = JSONObjectField(required=False)

    class Meta:
        model = LandingSection
        fields = (
            "id",
            "key",
            "section_type",
            "title",
            "subtitle",
            "content",
            "image",
            "cta_label",
            "cta_url",
            "display_order",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "created_at",
            "updated_at",
        )

    def validate_image(self, value):
        if value is None:
            return value
        return validate_image_upload(
            value,
            max_size_mb=8,
            file_label="Landing section image",
        )

    def validate_key(self, value):
        queryset = LandingSection.objects.filter(
            page__site_key="main",
            key=value,
        )
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError(
                "A section with this key already exists."
            )
        return value


class LandingPageSerializer(serializers.ModelSerializer):
    social_links = JSONObjectField(required=False)
    extra_settings = JSONObjectField(required=False)

    class Meta:
        model = LandingPage
        fields = (
            "id",
            "site_key",
            "site_name",
            "page_title",
            "meta_title",
            "meta_description",
            "canonical_url",
            "logo",
            "favicon",
            "og_image",
            "support_email",
            "support_phone",
            "social_links",
            "extra_settings",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "site_key",
            "created_at",
            "updated_at",
        )

    def validate_logo(self, value):
        if value is None:
            return value
        return validate_image_upload(
            value,
            max_size_mb=5,
            file_label="Landing logo",
        )

    def validate_favicon(self, value):
        if value is None:
            return value
        return validate_image_upload(
            value,
            max_size_mb=2,
            file_label="Landing favicon",
        )

    def validate_og_image(self, value):
        if value is None:
            return value
        return validate_image_upload(
            value,
            max_size_mb=8,
            file_label="Landing Open Graph image",
        )


class PublicLandingPageSerializer(LandingPageSerializer):
    sections = LandingSectionSerializer(many=True, read_only=True)

    class Meta(LandingPageSerializer.Meta):
        fields = LandingPageSerializer.Meta.fields + ("sections",)
