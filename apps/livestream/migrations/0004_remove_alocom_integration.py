from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("livestream", "0003_liveevent_provider_liveevent_provider_event_id_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="liveevent",
            name="provider",
        ),
        migrations.RemoveField(
            model_name="liveevent",
            name="provider_event_id",
        ),
        migrations.RemoveField(
            model_name="liveevent",
            name="provider_join_url",
        ),
        migrations.RemoveField(
            model_name="liveevent",
            name="provider_metadata",
        ),
        migrations.DeleteModel(
            name="AlocomSettings",
        ),
    ]
