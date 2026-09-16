from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class AssetRiskLevel(models.TextChoices):
    LOW = "LOW", "کم"
    LOW_MEDIUM = "LOW_MEDIUM", "کم تا متوسط"
    MEDIUM = "MEDIUM", "متوسط"
    MEDIUM_HIGH = "MEDIUM_HIGH", "متوسط تا بالا"
    HIGH = "HIGH", "بالا"
    VERY_HIGH = "VERY_HIGH", "بسیار بالا"
    NOT_TRADABLE = "NOT_TRADABLE", "متوسط / غیرقابل معامله"


class AssetUnit(models.TextChoices):
    GRAM = "GRAM", "گرم"
    COUNT = "COUNT", "عدد"
    SHARE = "SHARE", "واحد صندوق"
    CURRENCY_UNIT = "CURRENCY_UNIT", "واحد ارزی"
    ASSET_UNIT = "ASSET_UNIT", "واحد دارایی"
    INDEX_UNIT = "INDEX_UNIT", "واحد شاخص"


class AssetCategory(models.Model):
    code = models.SlugField(max_length=80, unique=True)
    title_fa = models.CharField(max_length=150)
    sort_order = models.PositiveIntegerField(default=0, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name_plural = "Asset categories"

    def __str__(self):
        return self.title_fa


class AssetCatalogItem(models.Model):
    code = models.SlugField(max_length=120, unique=True)
    category = models.ForeignKey(
        AssetCategory, on_delete=models.PROTECT, related_name="assets"
    )
    name_fa = models.CharField(max_length=200)
    risk_level = models.CharField(max_length=20, choices=AssetRiskLevel.choices)
    unit = models.CharField(max_length=20, choices=AssetUnit.choices)
    is_active = models.BooleanField(default=True, db_index=True)
    sort_order = models.PositiveIntegerField(default=0, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "id"]
        indexes = [
            models.Index(
                fields=["category", "is_active", "sort_order"],
                name="asset_catalog_active_order_idx",
            )
        ]

    def __str__(self):
        return self.name_fa


class UserAssetHolding(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="asset_holdings",
        db_index=True,
    )
    asset = models.ForeignKey(
        AssetCatalogItem, on_delete=models.PROTECT, related_name="holdings"
    )
    quantity = models.DecimalField(
        max_digits=28,
        decimal_places=8,
        validators=[MinValueValidator(0.00000001)],
    )
    unit = models.CharField(max_length=20, choices=AssetUnit.choices)
    note = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "asset"], name="uniq_user_asset_holding"
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0), name="asset_holding_quantity_gt_zero"
            ),
        ]
        indexes = [
            models.Index(fields=["user", "-updated_at"], name="holding_user_updated_idx")
        ]

    def __str__(self):
        return f"{self.user_id}: {self.asset.code}"

