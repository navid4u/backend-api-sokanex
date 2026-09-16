from rest_framework import serializers
from django.conf import settings
from django.utils.html import strip_tags

from common.validators import (
    validate_attachment_upload,
    validate_image_upload,
)
from common.content_access import AllowedLevelsSerializerMixin

from .models import (
    Direction,
    ManualSignalPost,
    Signal,
    SignalUpdate,
    VIPSignalPost,
)


class VIPSignalPostSerializer(serializers.ModelSerializer):
    kind = serializers.SerializerMethodField()
    channel_label = serializers.CharField(source="get_channel_display", read_only=True)
    excerpt = serializers.SerializerMethodField()

    class Meta:
        model = VIPSignalPost
        fields = (
            "id", "kind", "channel", "channel_label", "text", "excerpt",
            "image", "source", "published_at", "created_at",
        )
        read_only_fields = fields

    def get_excerpt(self, obj):
        words = obj.text.split()
        return " ".join(words[:30]) + ("…" if len(words) > 30 else "")

    def get_kind(self, obj):
        return "VIP_CHANNEL_POST"


class VIPSignalPostIngestionSerializer(serializers.Serializer):
    external_id = serializers.CharField(max_length=180, required=False, allow_blank=False)
    text = serializers.CharField(max_length=20000, allow_blank=False, trim_whitespace=True)
    image = serializers.ImageField(required=False, allow_null=True)
    published_at = serializers.DateTimeField(required=False)

    def validate_text(self, value):
        value = strip_tags(value).replace("\x00", "").strip()
        if not value:
            raise serializers.ValidationError("متن پست الزامی است.")
        return value

    def validate_image(self, value):
        return validate_image_upload(value, max_size_mb=8, file_label="VIP signal image")


class VIPSignalPostManagementSerializer(VIPSignalPostSerializer):
    class Meta(VIPSignalPostSerializer.Meta):
        fields = VIPSignalPostSerializer.Meta.fields + (
            "external_id", "is_active", "updated_at",
        )
        read_only_fields = (
            "id", "kind", "channel", "channel_label", "excerpt", "image",
            "source", "external_id", "published_at", "created_at", "updated_at",
        )

    def validate_text(self, value):
        value = strip_tags(value).replace("\x00", "").strip()
        if not value:
            raise serializers.ValidationError("متن پست الزامی است.")
        return value


class ManualSignalPostSerializer(serializers.ModelSerializer):
    kind = serializers.SerializerMethodField()
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = ManualSignalPost
        fields = (
            "id", "kind", "source", "text", "image", "author_name",
            "published_at", "created_at",
        )

    def to_internal_value(self, data):
        unexpected = set(data.keys()) - {"text", "image"}
        if unexpected:
            raise serializers.ValidationError({
                field: ["ارسال این فیلد مجاز نیست."] for field in sorted(unexpected)
            })
        return super().to_internal_value(data)
        read_only_fields = (
            "id", "kind", "source", "author_name", "published_at", "created_at",
        )

    def get_kind(self, obj) -> str:
        return "MANUAL_POST"

    def get_author_name(self, obj) -> str:
        return obj.author.get_full_name().strip() or obj.author.username

    def validate_text(self, value):
        return strip_tags(value).replace("\x00", "").strip()

    def validate_image(self, value):
        return validate_image_upload(value, max_size_mb=8, file_label="Manual signal image")

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if not attrs.get("text") and not attrs.get("image"):
            raise serializers.ValidationError(
                {"non_field_errors": ["حداقل یکی از متن یا تصویر الزامی است."]}
            )
        return attrs


class SignalUpdateSerializer(serializers.ModelSerializer):
    author = serializers.CharField(source="author.username", read_only=True)

    class Meta:
        model = SignalUpdate
        fields = ("id", "title", "message", "status", "image", "audio", "created_at", "updated_at", "author")
        read_only_fields = ("id", "created_at", "updated_at", "author")

    def validate_image(self, value):
        return validate_image_upload(value, max_size_mb=10, file_label="Signal update image")

    def validate_audio(self, value):
        allowed = {"audio/mpeg", "audio/mp4", "audio/wav", "audio/ogg", "audio/webm"}
        if getattr(value, "content_type", "").split(";", 1)[0].lower() not in allowed:
            raise serializers.ValidationError("Unsupported audio content type.")
        if value.size > 50 * 1024 * 1024:
            raise serializers.ValidationError("Audio cannot exceed 50 MB.")
        return value


class SignalListSerializer(
    AllowedLevelsSerializerMixin,
    serializers.ModelSerializer,
):

    trader = serializers.CharField(
        source="created_by.username",
        read_only=True,
    )

    class Meta:
        model = Signal

        fields = (
            "id",
            "signal_id",
            "title",
            "symbol",
            "market",
            "direction",
            "order_type",
            "timeframe",
            "entry_price",
            "take_profit",
            "stop_loss",
            "image",
            "status",
            "result_price",
            "result_percent",
            "closed_at",
            "description",
            "source",
            "external_id",
            "allowed_levels",
            "trader",
            "created_at",
        )


class SignalCreateSerializer(
    AllowedLevelsSerializerMixin,
    serializers.ModelSerializer,
):
    title = serializers.CharField(required=False, allow_blank=True, max_length=200)
    trader = serializers.CharField(source="created_by.username", read_only=True)

    class Meta:
        model = Signal

        fields = (
            "id",
            "signal_id",
            "title",
            "symbol",
            "market",
            "direction",
            "order_type",
            "timeframe",
            "entry_price",
            "stop_loss",
            "take_profit",
            "description",
            "image",
            "allowed_levels",
            "status",
            "trader",
            "created_at",
        )

        read_only_fields = (
            "id",
            "signal_id",
            "status",
            "trader",
            "created_at",
        )

    def validate_image(self, value):
        return validate_image_upload(
            value,
            max_size_mb=8,
            file_label="Signal image",
        )

    def validate(self, attrs):
        instance = self.instance

        direction = attrs.get(
            "direction",
            getattr(instance, "direction", None),
        )

        entry_price = attrs.get(
            "entry_price",
            getattr(instance, "entry_price", None),
        )

        stop_loss = attrs.get(
            "stop_loss",
            getattr(instance, "stop_loss", None),
        )

        take_profit = attrs.get(
            "take_profit",
            getattr(instance, "take_profit", None),
        )

        if direction == Direction.BUY:
            if not (
                stop_loss
                < entry_price
                < take_profit
            ):
                raise serializers.ValidationError(
                    {
                        "prices": (
                            "برای سیگنال خرید باید حد ضرر کمتر از قیمت ورود و "
                            "حد سود بیشتر از قیمت ورود باشد."
                        ),
                    }
                )

        elif direction == Direction.SELL:
            if not (
                take_profit
                < entry_price
                < stop_loss
            ):
                raise serializers.ValidationError(
                    {
                        "prices": (
                            "برای سیگنال فروش باید حد سود کمتر از قیمت ورود و "
                            "حد ضرر بیشتر از قیمت ورود باشد."
                        ),
                    }
                )

        if "title" in attrs:
            attrs["title"] = attrs["title"].strip()
        return attrs

    def create(self, validated_data):
        validated_data["symbol"] = validated_data["symbol"].strip().upper()
        if not validated_data.get("title"):
            direction_label = "خرید" if validated_data["direction"] == Direction.BUY else "فروش"
            validated_data["title"] = f"{validated_data['symbol']} - {direction_label}"
        return super().create(validated_data)


class SignalDetailSerializer(
    AllowedLevelsSerializerMixin,
    serializers.ModelSerializer,
):

    trader = serializers.CharField(
        source="created_by.username",
        read_only=True,
    )

    reviewed_by = serializers.CharField(
        source="approved_by.username",
        read_only=True,
        allow_null=True,
    )
    updates = SignalUpdateSerializer(many=True, read_only=True)

    class Meta:
        model = Signal

        fields = (
            "id",
            "signal_id",
            "title",
            "symbol",
            "market",
            "direction",
            "order_type",
            "timeframe",
            "entry_price",
            "stop_loss",
            "take_profit",
            "description",
            "image",
            "status",
            "rejection_reason",
            "result_price",
            "result_percent",
            "closed_at",
            "updates",
            "allowed_levels",
            "trader",
            "reviewed_by",
            "created_at",
            "updated_at",
            "source",
            "external_id",
        )


class SignalIngestionSerializer(serializers.Serializer):
    external_id = serializers.CharField(max_length=150, required=False, allow_blank=False)
    title = serializers.CharField(max_length=200, allow_blank=False, trim_whitespace=True)
    description = serializers.CharField(max_length=20000, allow_blank=False, trim_whitespace=True)
    image = serializers.ImageField(required=False, allow_null=True)

    def validate_image(self, value):
        return validate_image_upload(value, max_size_mb=settings.MEDIA_MAX_IMAGE_MB, file_label="Signal image")


class SignalManagementSerializer(SignalDetailSerializer):
    trader_id = serializers.IntegerField(source="created_by_id", read_only=True)

    class Meta(SignalDetailSerializer.Meta):
        fields = (
            "id", "title", "symbol", "market", "direction", "entry_price",
            "stop_loss", "take_profit", "description", "image", "status",
            "rejection_reason", "allowed_levels", "trader", "trader_id",
            "reviewed_by", "result_price", "result_percent", "closed_at",
            "created_at", "updated_at",
        )


class SignalEditSerializer(SignalCreateSerializer):
    status = serializers.ChoiceField(choices=Signal._meta.get_field("status").choices, required=False)
    result_price = serializers.DecimalField(max_digits=20, decimal_places=8, required=False, allow_null=True)
    result_percent = serializers.DecimalField(max_digits=10, decimal_places=4, required=False, allow_null=True)

    class Meta(SignalCreateSerializer.Meta):
        fields = SignalCreateSerializer.Meta.fields + (
            "status", "result_price", "result_percent",
        )

    def validate_status(self, value):
        request = self.context.get("request")
        if request and value != getattr(self.instance, "status", None):
            from apps.accounts.models import User
            if not request.user.has_platform_permission(User.Permission.SIGNAL_REVIEW):
                raise serializers.ValidationError("Only a signal reviewer can change signal status.")
            if value not in ("active", "successful", "failed", "cancelled"):
                raise serializers.ValidationError(
                    "Use the approve/reject endpoints for review decisions. Editing supports active, successful, failed or cancelled."
                )
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get("request")
        if request and any(key in attrs for key in ("result_price", "result_percent")):
            from apps.accounts.models import User
            if not request.user.has_platform_permission(User.Permission.SIGNAL_REVIEW):
                raise serializers.ValidationError({"result": "Only a signal reviewer can set result values."})
        return attrs
