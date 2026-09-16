from decimal import Decimal

from rest_framework import serializers

from .models import AssetCatalogItem, UserAssetHolding


class AssetCatalogItemSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="name_fa", read_only=True)
    category = serializers.CharField(source="category.code", read_only=True)
    category_label = serializers.CharField(source="category.title_fa", read_only=True)
    risk_level = serializers.CharField(source="get_risk_level_display", read_only=True)
    risk_code = serializers.CharField(source="risk_level", read_only=True)
    unit = serializers.CharField(source="get_unit_display", read_only=True)

    class Meta:
        model = AssetCatalogItem
        fields = (
            "code", "name", "category", "category_label",
            "risk_level", "risk_code", "unit",
        )


class AssetCatalogCategorySerializer(serializers.Serializer):
    code = serializers.CharField()
    title = serializers.CharField()
    unit = serializers.CharField(allow_null=True)
    assets = AssetCatalogItemSerializer(many=True)


class AssetCatalogResponseSerializer(serializers.Serializer):
    results = AssetCatalogCategorySerializer(many=True)


class UserAssetHoldingSerializer(serializers.ModelSerializer):
    asset_code = serializers.SlugRelatedField(
        source="asset",
        slug_field="code",
        queryset=AssetCatalogItem.objects.filter(is_active=True, category__is_active=True),
        error_messages={
            "does_not_exist": "دارایی فعال با این کد یافت نشد.",
            "invalid": "کد دارایی نامعتبر است.",
            "required": "کد دارایی الزامی است.",
        },
    )
    asset_name = serializers.CharField(source="asset.name_fa", read_only=True)
    category = serializers.CharField(source="asset.category.code", read_only=True)
    category_label = serializers.CharField(source="asset.category.title_fa", read_only=True)
    risk_level = serializers.CharField(source="asset.get_risk_level_display", read_only=True)
    risk_code = serializers.CharField(source="asset.risk_level", read_only=True)
    unit = serializers.CharField(required=False, allow_blank=True)
    quantity = serializers.DecimalField(
        max_digits=28,
        decimal_places=8,
        error_messages={
            "required": "مقدار دارایی الزامی است.",
            "invalid": "مقدار دارایی باید عدد معتبر باشد.",
            "max_digits": "تعداد ارقام مقدار دارایی بیش از حد مجاز است.",
            "max_decimal_places": "مقدار دارایی حداکثر می‌تواند ۸ رقم اعشار داشته باشد.",
        },
    )
    note = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=500,
        error_messages={"max_length": "یادداشت نمی‌تواند بیشتر از ۵۰۰ کاراکتر باشد."},
    )

    class Meta:
        model = UserAssetHolding
        fields = (
            "id", "asset_code", "asset_name", "category", "category_label",
            "risk_level", "risk_code", "quantity", "unit", "note",
            "created_at", "updated_at",
        )
        read_only_fields = (
            "id", "asset_name", "category", "category_label", "risk_level",
            "risk_code", "created_at", "updated_at",
        )

    def to_internal_value(self, data):
        allowed = {"quantity", "note"} if self.instance else {"asset_code", "quantity", "unit", "note"}
        unexpected = set(data.keys()) - allowed
        if unexpected:
            raise serializers.ValidationError({
                key: ["ارسال یا تغییر این فیلد مجاز نیست."] for key in sorted(unexpected)
            })
        return super().to_internal_value(data)

    def validate_quantity(self, value):
        if value <= Decimal("0"):
            raise serializers.ValidationError("مقدار دارایی باید بزرگ‌تر از صفر باشد.")
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        asset = attrs.get("asset", getattr(self.instance, "asset", None))
        if asset:
            attrs["unit"] = asset.unit
        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["unit"] = instance.get_unit_display()
        return data
