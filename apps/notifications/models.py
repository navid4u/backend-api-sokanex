from django.conf import settings
from django.db import models


class Notification(models.Model):

    class Type(models.TextChoices):
        INFO = "INFO", "Information"
        SIGNAL = "SIGNAL", "Signal"
        ARTICLE = "ARTICLE", "Article"
        VIDEO = "VIDEO", "Video"
        SYSTEM = "SYSTEM", "System"

    title = models.CharField(
        max_length=200,
    )

    message = models.TextField()

    notification_type = models.CharField(
        max_length=20,
        choices=Type.choices,
        default=Type.INFO,
    )

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="personal_notifications",
    )

    target_role = models.CharField(
        max_length=20,
        blank=True,
    )

    target_url = models.CharField(
        max_length=500,
        blank=True,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_notifications",
    )

    is_active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-created_at"]

        indexes = [
            models.Index(
                fields=[
                    "recipient",
                    "-created_at",
                ]
            ),
            models.Index(
                fields=[
                    "target_role",
                    "-created_at",
                ]
            ),
            models.Index(
                fields=[
                    "is_active",
                    "-created_at",
                ]
            ),
        ]

    def __str__(self):
        return self.title


class NotificationRead(models.Model):

    notification = models.ForeignKey(
        Notification,
        on_delete=models.CASCADE,
        related_name="read_records",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_reads",
    )

    read_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "notification",
                    "user",
                ],
                name=(
                    "unique_notification_read_per_user"
                ),
            ),
        ]

    def __str__(self):
        return (
            f"{self.user} - "
            f"{self.notification}"
        )