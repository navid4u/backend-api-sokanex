from rest_framework import serializers

from .models import PlatformSettings, SystemContent


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

