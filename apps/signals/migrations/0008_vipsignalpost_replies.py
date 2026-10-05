from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("signals", "0007_vipsignalpost_audio_vipsignalpost_video")]

    operations = [
        migrations.AddField(
            model_name="vipsignalpost",
            name="parent",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="replies", to="signals.vipsignalpost",
            ),
        ),
        migrations.AddField(
            model_name="vipsignalpost",
            name="reply_to_external_id",
            field=models.CharField(blank=True, max_length=180, null=True),
        ),
        migrations.AddField(
            model_name="vipsignalpost",
            name="reply_snapshot",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddIndex(
            model_name="vipsignalpost",
            index=models.Index(
                fields=["channel", "reply_to_external_id"],
                name="vip_signal_reply_lookup_idx",
            ),
        ),
    ]
