from rest_framework import serializers

from .models import Signal


class SignalListSerializer(serializers.ModelSerializer):

    trader = serializers.CharField(
        source="created_by.username",
        read_only=True,
    )

    class Meta:
        model = Signal

        fields = (
            "id",
            "title",
            "symbol",
            "market",
            "direction",
            "entry_price",
            "take_profit",
            "stop_loss",
            "image",
            "status",
            "trader",
            "created_at",
        )


class SignalCreateSerializer(serializers.ModelSerializer):

    trader = serializers.CharField(
        source="created_by.username",
        read_only=True,
    )

    class Meta:
        model = Signal

        fields = (
            "id",
            "title",
            "symbol",
            "market",
            "direction",
            "entry_price",
            "stop_loss",
            "take_profit",
            "description",
            "image",
            "status",
            "trader",
            "created_at",
        )

        read_only_fields = (
            "id",
            "status",
            "trader",
            "created_at",
        )

    def validate(self, attrs):
        direction = attrs.get("direction")
        entry_price = attrs.get("entry_price")
        stop_loss = attrs.get("stop_loss")
        take_profit = attrs.get("take_profit")

        if direction == "buy" and not (
            stop_loss < entry_price < take_profit
        ):
            raise serializers.ValidationError(
                {
                    "prices": (
                        "For a buy signal, stop loss must be below "
                        "entry price and take profit must be above it."
                    )
                }
            )

        if direction == "sell" and not (
            take_profit < entry_price < stop_loss
        ):
            raise serializers.ValidationError(
                {
                    "prices": (
                        "For a sell signal, take profit must be below "
                        "entry price and stop loss must be above it."
                    )
                }
            )

        return attrs


class SignalDetailSerializer(serializers.ModelSerializer):

    trader = serializers.CharField(
        source="created_by.username",
        read_only=True,
    )

    reviewed_by = serializers.CharField(
        source="approved_by.username",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = Signal

        fields = (
            "id",
            "title",
            "symbol",
            "market",
            "direction",
            "entry_price",
            "stop_loss",
            "take_profit",
            "description",
            "image",
            "status",
            "rejection_reason",
            "trader",
            "reviewed_by",
            "created_at",
            "updated_at",
        )