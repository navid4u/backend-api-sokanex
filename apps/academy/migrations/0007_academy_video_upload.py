import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("academy", "0006_course_market"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AcademyVideoUpload",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("filename", models.CharField(max_length=200)),
                ("client_upload_id", models.UUIDField(blank=True, null=True)),
                ("expected_size", models.PositiveBigIntegerField()),
                ("expected_sha256", models.CharField(blank=True, max_length=64)),
                ("received_size", models.PositiveBigIntegerField(default=0)),
                ("status", models.CharField(choices=[("PENDING", "Pending"), ("COMPLETED", "Completed"), ("EXPIRED", "Expired"), ("CANCELLED", "Cancelled")], default="PENDING", max_length=12)),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("course", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="video_uploads", to="academy.course")),
                ("session", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="academy.coursesession")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="academy_video_uploads", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "indexes": [models.Index(fields=["user", "status", "expires_at"], name="academy_vid_user_id_51ecda_idx")],
                "constraints": [models.UniqueConstraint(fields=["user", "client_upload_id"], name="academy_video_client_upload_unique")],
            },
        ),
    ]
