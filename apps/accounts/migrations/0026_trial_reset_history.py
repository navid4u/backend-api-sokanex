import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [("accounts", "0025_registration_email_market_confirmation_trial_revoke")]

    operations = [
        migrations.AddField(
            model_name="trialgrant",
            name="invalidated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="trialgrant",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="trial_grants_v2",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddConstraint(
            model_name="trialgrant",
            constraint=models.UniqueConstraint(
                fields=("user",), condition=Q(invalidated_at__isnull=True), name="unique_current_trial_grant_v2"
            ),
        ),
        migrations.CreateModel(
            name="MarketAccessBaselineReset",
            fields=[
                ("key", models.CharField(max_length=64, primary_key=True, serialize=False)),
                ("operation_id", models.UUIDField(unique=True)),
                ("applied_at", models.DateTimeField(auto_now_add=True)),
                ("normal_users", models.PositiveIntegerField()),
                ("invalidated_trials", models.PositiveIntegerField()),
            ],
        ),
    ]
