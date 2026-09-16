from django.conf import settings
import django.core.validators
from django.db import migrations, models
import django.db.models.deletion
from decimal import Decimal


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="AssetCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.SlugField(max_length=80, unique=True)),
                ("title_fa", models.CharField(max_length=150)),
                ("sort_order", models.PositiveIntegerField(db_index=True, default=0)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["sort_order", "id"], "verbose_name_plural": "Asset categories"},
        ),
        migrations.CreateModel(
            name="AssetCatalogItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.SlugField(max_length=120, unique=True)),
                ("name_fa", models.CharField(max_length=200)),
                ("risk_level", models.CharField(choices=[("LOW", "کم"), ("LOW_MEDIUM", "کم تا متوسط"), ("MEDIUM", "متوسط"), ("MEDIUM_HIGH", "متوسط تا بالا"), ("HIGH", "بالا"), ("VERY_HIGH", "بسیار بالا"), ("NOT_TRADABLE", "متوسط / غیرقابل معامله")], max_length=20)),
                ("unit", models.CharField(choices=[("GRAM", "گرم"), ("COUNT", "عدد"), ("SHARE", "واحد صندوق"), ("CURRENCY_UNIT", "واحد ارزی"), ("ASSET_UNIT", "واحد دارایی"), ("INDEX_UNIT", "واحد شاخص")], max_length=20)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("sort_order", models.PositiveIntegerField(db_index=True, default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("category", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="assets", to="assets.assetcategory")),
            ],
            options={
                "ordering": ["sort_order", "id"],
                "indexes": [models.Index(fields=["category", "is_active", "sort_order"], name="asset_catalog_active_order_idx")],
            },
        ),
        migrations.CreateModel(
            name="UserAssetHolding",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantity", models.DecimalField(decimal_places=8, max_digits=28, validators=[django.core.validators.MinValueValidator(Decimal("1E-8"))])),
                ("unit", models.CharField(choices=[("GRAM", "گرم"), ("COUNT", "عدد"), ("SHARE", "واحد صندوق"), ("CURRENCY_UNIT", "واحد ارزی"), ("ASSET_UNIT", "واحد دارایی"), ("INDEX_UNIT", "واحد شاخص")], max_length=20)),
                ("note", models.CharField(blank=True, max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("asset", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="holdings", to="assets.assetcatalogitem")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="asset_holdings", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-updated_at", "-id"],
                "indexes": [models.Index(fields=["user", "-updated_at"], name="holding_user_updated_idx")],
                "constraints": [
                    models.UniqueConstraint(fields=("user", "asset"), name="uniq_user_asset_holding"),
                    models.CheckConstraint(condition=models.Q(("quantity__gt", 0)), name="asset_holding_quantity_gt_zero"),
                ],
            },
        ),
    ]
