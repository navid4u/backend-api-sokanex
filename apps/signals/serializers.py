from rest_framework import serializers

from common.validators import (
    validate_attachment_upload,
    validate_image_upload,
)
from common.content_access import AllowedLevelsSerializerMixin

from .models import (
    Direction,
    Signal,
    SignalUpdate,
)


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
            "allowed_levels",
            "trader",
            "created_at",
        )


class SignalCreateSerializer(
    AllowedLevelsSerializerMixin,
    serializers.ModelSerializer,
):

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
        )

        read_only_fields = (
            "id",
            "signal_id",
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
                            "For a buy signal, stop loss "
                            "must be below entry price and "
                            "take profit must be above it."
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
                            "For a sell signal, take profit "
                            "must be below entry price and "
                            "stop loss must be above it."
                        ),
                    }
                )

        return attrs


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
        )


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
