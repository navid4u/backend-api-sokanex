from django.db import migrations, models

import apps.chat.social_media


class Migration(migrations.Migration):
    dependencies = [("chat", "0008_chatroom_manager_chatroom_market_chatroom_topic_and_more")]

    operations = [
        migrations.AlterField(
            model_name="chatroom",
            name="image",
            field=models.ImageField(
                upload_to="chat/rooms/",
                storage=apps.chat.social_media.PrivateSocialStorage(),
                null=True,
                blank=True,
            ),
        ),
        migrations.AlterField(
            model_name="message",
            name="attachment",
            field=models.FileField(
                upload_to="chat/attachments/",
                storage=apps.chat.social_media.PrivateSocialStorage(),
                null=True,
                blank=True,
            ),
        ),
    ]
