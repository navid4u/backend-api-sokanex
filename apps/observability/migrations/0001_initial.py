import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="LogEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source", models.CharField(choices=[("backend", "Backend"), ("frontend", "Frontend")], db_index=True, max_length=12)),
                ("level", models.CharField(choices=[("info", "Info"), ("warning", "Warning"), ("error", "Error"), ("critical", "Critical")], db_index=True, max_length=10)),
                ("category", models.CharField(db_index=True, max_length=80)),
                ("message", models.CharField(max_length=1000)),
                ("error_type", models.CharField(blank=True, max_length=180)),
                ("stack_trace", models.TextField(blank=True)),
                ("request_id", models.CharField(blank=True, db_index=True, max_length=64)),
                ("client_event_id", models.CharField(blank=True, db_index=True, max_length=80)),
                ("method", models.CharField(blank=True, max_length=12)),
                ("path", models.CharField(blank=True, db_index=True, max_length=1000)),
                ("status_code", models.PositiveSmallIntegerField(blank=True, db_index=True, null=True)),
                ("duration_ms", models.PositiveIntegerField(blank=True, null=True)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.CharField(blank=True, max_length=500)),
                ("frontend_url", models.CharField(blank=True, max_length=1000)),
                ("release", models.CharField(blank=True, max_length=100)),
                ("context", models.JSONField(blank=True, default=dict)),
                ("is_resolved", models.BooleanField(db_index=True, default=False)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("resolved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="resolved_observability_events", to=settings.AUTH_USER_MODEL)),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="observability_events", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.AddConstraint(
            model_name="logevent",
            constraint=models.UniqueConstraint(condition=models.Q(("client_event_id", ""), _negated=True), fields=("source", "client_event_id"), name="unique_observability_client_event"),
        ),
        migrations.AddIndex(model_name="logevent", index=models.Index(fields=["source", "level", "-created_at"], name="observabili_source_8da8d0_idx")),
        migrations.AddIndex(model_name="logevent", index=models.Index(fields=["is_resolved", "-created_at"], name="observabili_is_reso_db6db7_idx")),
    ]
