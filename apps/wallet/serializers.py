import hashlib

from django.conf import settings
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import BankCard, Payment, PaymentProvider, Transaction, UpgradePlan, Wallet, Withdrawal
from .services import WalletService


class WalletPremiumSubscriptionSerializer(serializers.Serializer):
    active = serializers.BooleanField()
    tier = serializers.CharField(allow_null=True)
    plan_id = serializers.IntegerField(allow_null=True)
    purchased_at = serializers.DateTimeField(allow_null=True)


class WalletSerializer(serializers.ModelSerializer):

    balance = serializers.SerializerMethodField()
    balance_usd = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    display_currency = serializers.SerializerMethodField()
    premium_subscription = serializers.SerializerMethodField()

    class Meta:
        model = Wallet

        fields = (
            "id",
            "balance",
            "balance_usd",
            "currency",
            "display_currency",
            "premium_subscription",
            "updated_at",
        )

        read_only_fields = fields

    def get_balance(self, obj) -> int:
        return WalletService.balance_irt(obj)

    def get_display_currency(self, obj) -> str:
        return "USD"

    @extend_schema_field(WalletPremiumSubscriptionSerializer)
    def get_premium_subscription(self, obj) -> dict:
        return WalletService.premium_subscription(obj.user)


class TransactionSerializer(serializers.ModelSerializer):

    class Meta:
        model = Transaction

        fields = (
            "id",
            "reference",
            "transaction_type",
            "status",
            "amount",
            "balance_after",
            "description",
            "created_at",
        )

        read_only_fields = fields

class BankCardSerializer(serializers.ModelSerializer):
    card_number = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = BankCard
        fields = ("id", "title", "card_number", "card_last4", "iban", "is_verified", "created_at")
        read_only_fields = ("id", "card_last4", "is_verified", "created_at")

    def validate_card_number(self, value):
        digits = "".join(ch for ch in value if ch.isdigit())
        if len(digits) != 16:
            raise serializers.ValidationError("Card number must contain 16 digits.")
        return digits

    def validate_iban(self, value):
        value = value.replace(" ", "").upper()
        if value and (len(value) != 26 or not value.startswith("IR") or not value[2:].isdigit()):
            raise serializers.ValidationError("Enter a valid Iranian IBAN.")
        return value

    def create(self, validated_data):
        card = validated_data.pop("card_number", "")
        if card:
            validated_data["card_last4"] = card[-4:]
            validated_data["card_hash"] = hashlib.sha256((settings.SECRET_KEY + card).encode()).hexdigest()
        return BankCard.objects.create(user=self.context["request"].user, **validated_data)

    def validate(self, attrs):
        if not attrs.get("card_number") and not attrs.get("iban"):
            raise serializers.ValidationError("Provide a card number or IBAN.")
        return attrs


class WithdrawalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Withdrawal
        fields = ("id", "bank_card", "amount_irt", "status", "created_at", "updated_at")
        read_only_fields = ("id", "status", "created_at", "updated_at")

    def validate_amount_irt(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be positive.")
        return value


class PaymentProviderSerializer(serializers.ModelSerializer):
    merchant_configured = serializers.SerializerMethodField()
    api_key_configured = serializers.SerializerMethodField()

    class Meta:
        model = PaymentProvider
        fields = ("id", "code", "title", "is_active", "sandbox", "sort_order", "merchant_configured", "api_key_configured", "updated_at")
        read_only_fields = ("id", "code", "title", "merchant_configured", "api_key_configured", "updated_at")

    def get_merchant_configured(self, obj) -> bool:
        return bool(settings.ZARINPAL_MERCHANT_ID) if obj.code == "ZARINPAL" else False

    def get_api_key_configured(self, obj) -> bool:
        return bool(settings.IDPAY_API_KEY) if obj.code == "IDPAY" else False

    def validate(self, attrs):
        attrs = super().validate(attrs)
        active = attrs.get("is_active", getattr(self.instance, "is_active", False))
        if active and self.instance:
            if self.instance.code == "ZARINPAL" and not settings.ZARINPAL_MERCHANT_ID:
                raise serializers.ValidationError({"is_active": "Configure ZARINPAL_MERCHANT_ID on the server first."})
            if self.instance.code == "IDPAY" and not settings.IDPAY_API_KEY:
                raise serializers.ValidationError({"is_active": "Configure IDPAY_API_KEY on the server first."})
        return attrs


class PaymentCreateSerializer(serializers.Serializer):
    provider = serializers.SlugRelatedField(slug_field="code", queryset=PaymentProvider.objects.filter(is_active=True))
    amount_irt = serializers.IntegerField(min_value=1)
    purpose = serializers.ChoiceField(choices=Payment.Purpose.choices)
    idempotency_key = serializers.CharField(max_length=120)
    metadata = serializers.JSONField(required=False)


class PaymentVerifySerializer(serializers.Serializer):
    payment_id = serializers.UUIDField()
    authority = serializers.CharField(max_length=120)
    status = serializers.CharField(required=False, allow_blank=True)


class UpgradePlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = UpgradePlan
        fields = (
            "id", "level", "plan_type", "title", "description", "price_irt",
            "price_usd", "active", "features", "sort_order",
        )
        read_only_fields = ("id", "level", "plan_type")
