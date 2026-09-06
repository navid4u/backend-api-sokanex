from django.conf import settings
from django.db import models


class LogEvent(models.Model):
    class Source(models.TextChoices):
        BACKEND = "backend", "Backend"
        FRONTEND = "frontend", "Frontend"

    class Level(models.TextChoices):
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        ERROR = "error", "Error"
        CRITICAL = "critical", "Critical"

    source = models.CharField(max_length=12, choices=Source.choices, db_index=True)
    level = models.CharField(max_length=10, choices=Level.choices, db_index=True)
    category = models.CharField(max_length=80, db_index=True)
    message = models.CharField(max_length=1000)
    error_type = models.CharField(max_length=180, blank=True)
    stack_trace = models.TextField(blank=True)
    request_id = models.CharField(max_length=64, blank=True, db_index=True)
    client_event_id = models.CharField(max_length=80, blank=True, db_index=True)
    method = models.CharField(max_length=12, blank=True)
    path = models.CharField(max_length=1000, blank=True, db_index=True)
    status_code = models.PositiveSmallIntegerField(null=True, blank=True, db_index=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="observability_events",
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    frontend_url = models.CharField(max_length=1000, blank=True)
    release = models.CharField(max_length=100, blank=True)
    context = models.JSONField(default=dict, blank=True)
    is_resolved = models.BooleanField(default=False, db_index=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="resolved_observability_events",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "client_event_id"],
                condition=~models.Q(client_event_id=""),
                name="unique_observability_client_event",
            )
        ]
        indexes = [
            models.Index(fields=["source", "level", "-created_at"]),
            models.Index(fields=["is_resolved", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.source}:{self.level}:{self.category} ({self.pk})"
