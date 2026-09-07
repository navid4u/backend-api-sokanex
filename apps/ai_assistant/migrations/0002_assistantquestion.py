import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ai_assistant", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="AssistantQuestion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("question", models.TextField(validators=[django.core.validators.MaxLengthValidator(12000)])),
                ("client_message_id", models.CharField(blank=True, max_length=80)),
                ("provider_succeeded", models.BooleanField(db_index=True, default=False)),
                ("provider_status_code", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="assistant_questions", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.AddConstraint(
            model_name="assistantquestion",
            constraint=models.UniqueConstraint(condition=models.Q(("client_message_id", ""), _negated=True), fields=("user", "client_message_id"), name="unique_assistant_question_client_message"),
        ),
        migrations.AddIndex(
            model_name="assistantquestion",
            index=models.Index(fields=["user", "-created_at"], name="ai_assistan_user_id_bb2cab_idx"),
        ),
    ]
