import apps.accounts.models
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


SECTION_CHOICES = [
    ("ARTICLES", "Articles"),
    ("VIDEOS", "Videos"),
    ("LIVESTREAMS", "Livestreams"),
]


class Migration(migrations.Migration):
    dependencies = [("accounts", "0022_market_access_v2_foundation")]

    operations = [
        migrations.CreateModel(
            name="ContentSectionAccessPolicy",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("section", models.CharField(choices=SECTION_CHOICES, max_length=16, unique=True)),
                ("allowed_tiers", models.JSONField(default=apps.accounts.models.default_content_access_tiers)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="content_section_policy_updates_v2", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="ContentSectionAccessAudit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("section", models.CharField(choices=SECTION_CHOICES, max_length=16)),
                ("before", models.JSONField(default=list)),
                ("after", models.JSONField(default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="content_section_policy_audits_v2", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-created_at", "-id")},
        ),
    ]
