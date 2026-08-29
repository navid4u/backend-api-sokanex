import re
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from rest_framework import serializers

from .crypto import encrypt_token
from .models import AISettings


def clean_content(value):
    value = re.sub(r"<script\b[^>]*>.*?</script>", "", value, flags=re.I | re.S)
    return re.sub(r"<[^>]+>", "", value).strip()


class AISettingsSerializer(serializers.ModelSerializer):
    token_configured = serializers.SerializerMethodField()
    api_token = serializers.CharField(write_only=True, required=False, allow_blank=True, trim_whitespace=False)

    class Meta:
        model = AISettings
        fields = (
            "enabled", "provider", "base_url", "token_configured", "api_token", "model",
            "financial_system_prompt", "technical_system_prompt", "temperature", "max_tokens",
            "daily_user_limit", "image_daily_user_limit", "request_timeout",
        )

    def get_token_configured(self, obj) -> bool:
        return bool(obj.api_token_encrypted)

    def validate_base_url(self, value):
        if not value.startswith("https://"):
            raise serializers.ValidationError("Only HTTPS provider URLs are accepted.")
        return value.rstrip("/")

    def update(self, instance, validated_data):
        token = validated_data.pop("api_token", None)
        if token:
            instance.api_token_encrypted = encrypt_token(token)
        return super().update(instance, validated_data)


class ChatMessageSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=("user", "assistant"))
    content = serializers.CharField(max_length=12000, trim_whitespace=True)

    def validate_content(self, value):
        cleaned = clean_content(value)
        if not cleaned:
            raise serializers.ValidationError("Message content cannot be empty.")
        return cleaned


class AssistantChatSerializer(serializers.Serializer):
    messages = ChatMessageSerializer(many=True, allow_empty=False)

    def validate_messages(self, value):
        if len(value) > 20:
            raise serializers.ValidationError("At most 20 messages are accepted.")
        if sum(len(item["content"]) for item in value) > 12000:
            raise serializers.ValidationError("Conversation exceeds 12000 characters.")
        return value


class TechnicalAnalysisSerializer(serializers.Serializer):
    image = serializers.FileField()

    def validate_image(self, value):
        if value.size > 1024 * 1024:
            from .exceptions import AssistantError
            raise AssistantError("حجم تصویر باید حداکثر یک مگابایت باشد.", "IMAGE_TOO_LARGE", 413)
        allowed = {"image/jpeg": (b"\xff\xd8\xff",), "image/png": (b"\x89PNG\r\n\x1a\n",), "image/webp": (b"RIFF",)}
        head = value.read(12)
        value.seek(0)
        content_type = (getattr(value, "content_type", "") or "").lower()
        valid = content_type in allowed and any(head.startswith(magic) for magic in allowed[content_type])
        if content_type == "image/webp":
            valid = valid and head[8:12] == b"WEBP"
        if not valid:
            from .exceptions import AssistantError
            raise AssistantError("فرمت تصویر معتبر نیست.", "INVALID_IMAGE_TYPE", 400)
        try:
            parsed = Image.open(BytesIO(value.read()))
            parsed.verify()
            width, height = parsed.size
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            from .exceptions import AssistantError
            raise AssistantError("فایل تصویر قابل پردازش نیست.", "INVALID_IMAGE_TYPE", 400) from exc
        finally:
            value.seek(0)
        if width > 10000 or height > 10000 or width * height > 40_000_000:
            raise serializers.ValidationError("Image dimensions are too large.")
        return value
