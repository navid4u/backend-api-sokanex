from django.db import migrations, models

import apps.chat.social_media


class Migration(migrations.Migration):
    dependencies = [("chat", "0006_supportmessage_idempotency_key_and_more")]

    operations = [
        migrations.AlterField(
            model_name="traderpost",
            name="image",
            field=models.ImageField(
                upload_to="social/posts/images/%Y/%m/",
                storage=apps.chat.social_media.PrivateSocialStorage(),
                null=True,
                blank=True,
            ),
        ),
        migrations.AlterField(
            model_name="traderpost",
            name="video",
            field=models.FileField(
                upload_to="social/posts/videos/%Y/%m/",
                storage=apps.chat.social_media.PrivateSocialStorage(),
                null=True,
                blank=True,
            ),
        ),
    ]
