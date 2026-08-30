import json
import re

from django.conf import settings
from rest_framework import serializers

from .models import PlatformSettings, SystemContent, UITranslationCatalog


class PublicPlatformSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlatformSettings
        fields = ("site_name", "support_email", "support_phone", "maintenance_mode", "updated_at")


class FinancialSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlatformSettings
        fields = (
            "minimum_deposit_irt", "minimum_withdrawal_irt",
            "maximum_withdrawal_irt", "withdrawal_fee_irt", "updated_at",
        )
        read_only_fields = ("updated_at",)

    def validate(self, attrs):
        minimum = attrs.get("minimum_withdrawal_irt", getattr(self.instance, "minimum_withdrawal_irt", 0))
        maximum = attrs.get("maximum_withdrawal_irt", getattr(self.instance, "maximum_withdrawal_irt", 0))
        if minimum > maximum:
            raise serializers.ValidationError({"maximum_withdrawal_irt": "Must be at least the minimum withdrawal."})
        return attrs


class SystemContentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemContent
        fields = ("key", "section", "label", "value", "multiline", "updated_at")
        read_only_fields = ("key", "section", "label", "multiline", "updated_at")


HTML_PATTERN = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>")


class UITranslationCatalogSerializer(serializers.ModelSerializer):
    class Meta:
        model = UITranslationCatalog
        fields = ("locale", "version", "translations", "updated_at")
        read_only_fields = fields


class UITranslationReplaceSerializer(serializers.Serializer):
    translations = serializers.DictField()

    def validate_translations(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Translations must be a JSON object.")
        clean = {}
        for key, translation in value.items():
            if not isinstance(key, str) or not key.strip():
                raise serializers.ValidationError("Translation keys must be non-empty strings.")
            if len(key) > 500:
                raise serializers.ValidationError("Translation keys may contain at most 500 characters.")
            if not isinstance(translation, str):
                raise serializers.ValidationError(f"Translation for {key!r} must be a string.")
            if len(translation) > 1000:
                raise serializers.ValidationError(f"Translation for {key!r} may contain at most 1000 characters.")
            if HTML_PATTERN.search(key) or HTML_PATTERN.search(translation):
                raise serializers.ValidationError("HTML and script markup are not allowed.")
            clean[key.strip()] = translation.strip()
        encoded = json.dumps(clean, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > settings.TRANSLATIONS_MAX_PAYLOAD_BYTES:
            raise serializers.ValidationError("Translation payload is too large.")
        return clean
