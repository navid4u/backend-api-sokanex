from django.db import migrations, models


def preserve_successful_pending_challenges(apps, schema_editor):
    OTPChallenge = apps.get_model("accounts", "OTPChallenge")
    for challenge in OTPChallenge.objects.filter(
        consumed_at__isnull=True,
        locked_at__isnull=True,
        sent_at__isnull=True,
    ).iterator():
        challenge.sent_at = challenge.created_at
        challenge.save(update_fields=["sent_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0015_upgraderequest_price_snapshot_usd_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="otpchallenge",
            name="sent_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.RunPython(
            preserve_successful_pending_challenges,
            migrations.RunPython.noop,
        ),
    ]
