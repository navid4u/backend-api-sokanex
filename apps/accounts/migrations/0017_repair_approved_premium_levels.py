from django.db import migrations


def repair_approved_premium_levels(apps, schema_editor):
    UpgradeRequest = apps.get_model("accounts", "UpgradeRequest")
    User = apps.get_model("accounts", "User")
    user_ids = UpgradeRequest.objects.filter(
        request_type="PREMIUM",
        status="APPROVED",
    ).values_list("user_id", flat=True)
    User.objects.filter(pk__in=user_ids).exclude(access_level=5).update(access_level=5)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0016_otpchallenge_sent_at")]

    operations = [migrations.RunPython(repair_approved_premium_levels, migrations.RunPython.noop)]
