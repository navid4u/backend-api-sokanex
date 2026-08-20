from django.conf import settings
from django.db import models
from common.content_access import LevelRestrictedContent


class Notification(LevelRestrictedContent, models.Model):

    class Type(models.TextChoices):
        INFO = "INFO", "Information"
        SIGNAL = "SIGNAL", "Signal"
        ARTICLE = "ARTICLE", "Article"
        VIDEO = "VIDEO", "Video"
        SYSTEM = "SYSTEM", "System"
        SOCIAL = "SOCIAL", "Social"
        ACADEMY = "ACADEMY", "Academy"
        SECURITY = "SECURITY", "Security"

    class Priority(models.TextChoices):
        LOW = "LOW", "Low"
        NORMAL = "NORMAL", "Normal"
        HIGH = "HIGH", "High"
        URGENT = "URGENT", "Urgent"

    title = models.CharField(
        max_length=200,
    )

    message = models.TextField()

    notification_type = models.CharField(
        max_length=20,
        choices=Type.choices,
        default=Type.INFO,
    )
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.NORMAL)
    action_label = models.CharField(max_length=80, blank=True)
    send_sms = models.BooleanField(default=False)
    image = models.ImageField(upload_to="notifications/images/", null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

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
            models.Index(fields=["is_active", "expires_at", "-created_at"]),
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


class NotificationSMSDelivery(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SENT = "SENT", "Sent"
        FAILED = "FAILED", "Failed"

    notification = models.ForeignKey(
        Notification, on_delete=models.CASCADE, related_name="sms_deliveries"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="notification_sms_deliveries",
    )
    phone = models.CharField(max_length=20)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    provider_message_id = models.CharField(max_length=100, blank=True)
    provider_code = models.CharField(max_length=50, blank=True)
    error_message = models.CharField(max_length=500, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["notification", "user"], name="unique_notification_sms_per_user"
        )]
        indexes = [models.Index(fields=["status", "attempts", "created_at"])]
