from django.db import migrations, models


def seed_locks(apps, schema_editor):
    Lock = apps.get_model("signals", "VIPChannelRetention")
    for channel in ("CRYPTO", "FOREX"):
        Lock.objects.get_or_create(channel=channel)


class Migration(migrations.Migration):
    dependencies = [("signals", "0008_vipsignalpost_replies")]

    operations = [
        migrations.AlterModelOptions(
            name="vipsignalpost",
            options={"ordering": ["-published_at", "-created_at", "-id"]},
        ),
        migrations.CreateModel(
            name="VIPChannelRetention",
            fields=[
                ("channel", models.CharField(choices=[("CRYPTO", "کانال وی آی پی سوکانکس (کریپتو)"), ("FOREX", "کانال وی آی پی سوکانکس (فارکس)")], max_length=10, primary_key=True, serialize=False)),
                ("activated_at", models.DateTimeField(blank=True, null=True)),
            ],
        ),
        migrations.RunPython(seed_locks, migrations.RunPython.noop),
    ]
