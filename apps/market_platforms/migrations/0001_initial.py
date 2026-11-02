import apps.market_platforms.models
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def seed_fields(apps, schema_editor):
    Field = apps.get_model("market_platforms", "FieldDefinition")
    groups = {
        "BROKER": [
            ("regulation", "رگولاتوری"), ("account_types", "انواع حساب"),
            ("minimum_deposit", "حداقل واریز"), ("spread_commission", "اسپرد و کمیسیون"),
            ("leverage", "اهرم معاملاتی"), ("trading_platforms", "پلتفرم‌های معاملاتی (MT4 / MT5)"),
            ("deposit_withdrawal", "واریز و برداشت"), ("iranian_users", "شرایط کاربران ایرانی"),
            ("pros", "مزایا"), ("cons", "معایب"),
        ],
        "EXCHANGE": [
            ("country_regulation", "کشور و رگولاتوری"), ("spot_futures", "اسپات و فیوچرز"),
            ("supported_coins", "ارزهای پشتیبانی‌شده"), ("trading_fees", "کارمزد معاملات"),
            ("withdrawal_fees", "کارمزد برداشت"), ("kyc", "احراز هویت (KYC)"),
            ("security", "امنیت"), ("iranian_users", "شرایط کاربران ایرانی"),
            ("pros", "مزایا"), ("cons", "معایب"),
        ],
    }
    for platform_type, rows in groups.items():
        for sort_order, (key, label) in enumerate(rows):
            Field.objects.using(schema_editor.connection.alias).get_or_create(
                platform_type=platform_type, key=key,
                defaults={"label": label, "sort_order": sort_order},
            )


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="Platform",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("platform_type", models.CharField(choices=[("BROKER", "Broker"), ("EXCHANGE", "Exchange")], max_length=8)),
                ("name", models.CharField(max_length=120)),
                ("subtitle", models.CharField(blank=True, max_length=180)),
                ("description", models.TextField(blank=True)),
                ("logo", models.ImageField(blank=True, null=True, upload_to=apps.market_platforms.models.platform_logo_path)),
                ("rating", models.DecimalField(blank=True, decimal_places=1, max_digits=2, null=True)),
                ("official_url", models.URLField(blank=True, max_length=2048)),
                ("registration_url", models.URLField(blank=True, max_length=2048)),
                ("is_active", models.BooleanField(default=True)),
                ("is_popular", models.BooleanField(default=False)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("details", models.JSONField(blank=True, default=dict)),
                ("deleted_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ("sort_order", "-rating", "id"),
                     "indexes": [models.Index(fields=["platform_type", "is_active", "sort_order"], name="mp_type_active_sort_idx")]},
        ),
        migrations.CreateModel(
            name="FieldDefinition",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("platform_type", models.CharField(choices=[("BROKER", "Broker"), ("EXCHANGE", "Exchange")], max_length=8)),
                ("key", models.CharField(max_length=64)),
                ("label", models.CharField(max_length=120)),
                ("is_active", models.BooleanField(default=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
            ],
            options={"ordering": ("sort_order", "id"),
                     "constraints": [models.UniqueConstraint(fields=("platform_type", "key"), name="unique_market_platform_field")]},
        ),
        migrations.CreateModel(
            name="PlatformChangeAudit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(max_length=20)),
                ("object_id", models.PositiveBigIntegerField()),
                ("object_type", models.CharField(max_length=20)),
                ("changed_fields", models.JSONField(default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ("field_definition", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="market_platforms.fielddefinition")),
                ("platform", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="market_platforms.platform")),
            ],
        ),
        migrations.RunPython(seed_fields, migrations.RunPython.noop),
    ]
