import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image, UnidentifiedImageError
from rest_framework import serializers
from rest_framework.fields import empty

from .models import FieldDefinition, Platform


KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
RESERVED_KEYS = {"constructor", "prototype", "__proto__"}
IMAGE_FORMATS = {"JPEG": {".jpg", ".jpeg"}, "PNG": {".png"}, "WEBP": {".webp"}}
IMAGE_MIMES = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


class OmissionBooleanField(serializers.BooleanField):
    def get_value(self, dictionary):
        if self.field_name not in dictionary:
            return empty
        return super().get_value(dictionary)


class DetailsField(serializers.JSONField):
    def to_internal_value(self, data):
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (ValueError, TypeError) as exc:
                raise serializers.ValidationError("Value must be valid JSON object.") from exc
        if not isinstance(data, dict):
            raise serializers.ValidationError("Value must be a JSON object.")
        return data


class PlatformReadSerializer(serializers.ModelSerializer):
    logo = serializers.SerializerMethodField()
    details = serializers.SerializerMethodField()

    class Meta:
        model = Platform
        fields = ("id", "platform_type", "name", "subtitle", "description", "logo", "rating",
                  "official_url", "registration_url", "is_active", "is_popular", "sort_order",
                  "details", "updated_at")

    def get_logo(self, obj):
        if not obj.logo:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(obj.logo.url) if request else obj.logo.url

    def get_details(self, obj):
        if self.context.get("manage"):
            return obj.details
        cache = self.context.setdefault("_active_detail_keys", {})
        if obj.platform_type not in cache:
            cache[obj.platform_type] = set(FieldDefinition.objects.filter(
                platform_type=obj.platform_type, is_active=True,
            ).values_list("key", flat=True))
        return {key: value for key, value in obj.details.items() if key in cache[obj.platform_type]}


class PlatformWriteSerializer(serializers.ModelSerializer):
    details = DetailsField(required=False)
    is_active = OmissionBooleanField(required=False)
    is_popular = OmissionBooleanField(required=False)
    remove_logo = OmissionBooleanField(required=False, write_only=True, default=False)

    class Meta:
        model = Platform
        fields = ("id", "platform_type", "name", "subtitle", "description", "logo", "rating",
                  "official_url", "registration_url", "is_active", "is_popular", "sort_order",
                  "details", "remove_logo", "updated_at")
        read_only_fields = ("id", "updated_at")
        extra_kwargs = {"rating": {"required": False, "allow_null": True}}

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Name is required.")
        return value.strip()

    def validate_description(self, value):
        if len(value) > 10000:
            raise serializers.ValidationError("Description cannot exceed 10000 characters.")
        return value

    def validate_rating(self, value):
        if value is not None and not 1 <= value <= 5:
            raise serializers.ValidationError("Rating must be from 1 to 5.")
        return value

    def _validate_url(self, value):
        if not value:
            return value
        try:
            parts = urlsplit(value)
        except ValueError as exc:
            raise serializers.ValidationError("Use a valid absolute HTTP/HTTPS URL.") from exc
        if parts.scheme.lower() not in ("http", "https") or not parts.hostname or parts.username or parts.password:
            raise serializers.ValidationError("Use an absolute HTTP/HTTPS URL without credentials.")
        return value

    def validate_official_url(self, value):
        return self._validate_url(value)

    def validate_registration_url(self, value):
        return self._validate_url(value)

    def validate_logo(self, value):
        if value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError("Logo cannot exceed 5 MiB.")
        extension = Path(value.name).suffix.lower()
        if extension not in {".jpg", ".jpeg", ".png", ".webp"}:
            raise serializers.ValidationError("Logo must be PNG, JPEG or WebP.")
        position = value.tell()
        try:
            value.seek(0)
            with Image.open(value) as image:
                image_format = image.format
                if image_format not in IMAGE_FORMATS or extension not in IMAGE_FORMATS[image_format]:
                    raise serializers.ValidationError("Logo content does not match its extension.")
                if image.width * image.height > 25_000_000:
                    raise serializers.ValidationError("Logo dimensions are too large.")
                image.load()
        except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as exc:
            raise serializers.ValidationError("Logo is not a valid image.") from exc
        finally:
            value.seek(position)
        if getattr(value, "content_type", "").split(";", 1)[0].lower() != IMAGE_MIMES[image_format]:
            raise serializers.ValidationError("Logo MIME type does not match its content.")
        return value

    def validate(self, attrs):
        kind = attrs.get("platform_type", getattr(self.instance, "platform_type", None))
        if self.instance and kind != self.instance.platform_type:
            raise serializers.ValidationError({"platform_type": "Platform type cannot change."})
        if attrs.get("remove_logo") and attrs.get("logo"):
            raise serializers.ValidationError({"logo": "Cannot upload and remove a logo together."})
        if "details" in attrs:
            known = set(FieldDefinition.objects.filter(platform_type=kind).values_list("key", flat=True))
            details = {}
            for key, value in attrs["details"].items():
                if key not in known:
                    raise serializers.ValidationError({"details": f"Unknown field: {key}"})
                if value is None:
                    value = ""
                if not isinstance(value, str) or len(value) > 2000:
                    raise serializers.ValidationError({"details": f"{key} must be text of at most 2000 characters."})
                details[key] = value
            attrs["details"] = {**(self.instance.details if self.instance else {}), **details}
        return attrs

    def create(self, validated_data):
        validated_data.pop("remove_logo", None)
        self._changed_fields = list(validated_data)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        remove_logo = validated_data.pop("remove_logo", False)
        if remove_logo:
            validated_data["logo"] = None
        changed = [key for key, value in validated_data.items() if getattr(instance, key) != value]
        self._changed_fields = changed
        if not changed:
            return instance
        return super().update(instance, validated_data)


class FieldDefinitionSerializer(serializers.ModelSerializer):
    is_active = OmissionBooleanField(required=False)

    class Meta:
        model = FieldDefinition
        fields = ("id", "platform_type", "key", "label", "is_active", "sort_order")
        read_only_fields = ("id",)

    def validate_key(self, value):
        if not KEY_RE.fullmatch(value) or value in RESERVED_KEYS:
            raise serializers.ValidationError("Use a safe lowercase field key.")
        return value

    def validate_label(self, value):
        if not value.strip():
            raise serializers.ValidationError("Label is required.")
        return value.strip()

    def validate(self, attrs):
        if self.instance:
            for name in ("platform_type", "key"):
                if name in attrs and attrs[name] != getattr(self.instance, name):
                    raise serializers.ValidationError({name: "This field cannot change."})
        elif FieldDefinition.objects.filter(platform_type=attrs.get("platform_type"), key=attrs.get("key")).exists():
            raise serializers.ValidationError({"key": "This key already exists for this platform type."})
        return attrs
