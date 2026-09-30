from django.db import migrations


def normalize_permanent_gold(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    UpgradeRequest = apps.get_model("accounts", "UpgradeRequest")
    database = schema_editor.connection.alias

    User.objects.using(database).filter(
        gold_permanent_granted_at__isnull=False,
    ).exclude(access_level=5).update(access_level=5)

    UpgradeRequest.objects.using(database).filter(
        request_type="PREMIUM",
        grant_source="GOLD_RENEWAL_REQUEST",
    ).exclude(requested_level=5).update(requested_level=5)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0020_upgraderequest_market_type")]

    operations = [migrations.RunPython(normalize_permanent_gold, migrations.RunPython.noop)]
