from datetime import time

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


class WebPushSubscription(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="web_push_subscriptions",
    )
    endpoint = models.URLField(max_length=2048, unique=True)
    p256dh = models.CharField(max_length=256)
    auth = models.CharField(max_length=128)
    user_agent = models.CharField(max_length=500, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-last_seen_at",)

    def __str__(self):
        return f"Web Push subscription for user {self.user_id}"


class NotificationPushDelivery(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SENT = "SENT", "Sent"
        FAILED = "FAILED", "Failed"

    notification = models.ForeignKey(
        Notification, on_delete=models.CASCADE, related_name="push_deliveries"
    )
    subscription = models.ForeignKey(
        WebPushSubscription, on_delete=models.CASCADE, related_name="deliveries"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="notification_push_deliveries",
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    provider_status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    error_code = models.CharField(max_length=80, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=("notification", "subscription"), name="unique_notification_push_per_subscription"
        )]
        indexes = [models.Index(fields=("status", "attempts", "created_at"), name="notif_push_status_4d971b_idx")]


class SMSAutomationRule(models.Model):
    """Editable copy and timing for one event/market variant; disabled by default."""

    class Event(models.TextChoices):
        WELCOME = "WELCOME", "Registration welcome"
        ACCESS_CHANGE = "ACCESS_CHANGE", "Access changed"
        TRIAL = "TRIAL", "Trial day"

    class Market(models.TextChoices):
        ALL = "ALL", "All markets / fallback"
        INTERNAL = "internal", "Internal"
        FOREX = "forex", "Forex"
        CRYPTO = "crypto", "Crypto"

    event = models.CharField(max_length=20, choices=Event.choices)
    market = models.CharField(max_length=12, choices=Market.choices, default=Market.ALL)
    slot = models.CharField(max_length=24)  # WELCOME, ACCESS_CHANGE, TRIAL_1..TRIAL_7
    trial_day = models.PositiveSmallIntegerField(null=True, blank=True)
    text = models.CharField(max_length=500)
    enabled = models.BooleanField(default=False)
    send_time_utc = models.TimeField(default=time(9, 0))
    delay_minutes = models.PositiveIntegerField(default=0)
    enabled_at = models.DateTimeField(null=True, blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="sms_automation_rules_edited",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("event", "slot", "market")
        constraints = [models.UniqueConstraint(
            fields=("slot", "market"), name="unique_sms_automation_slot_market"
        )]

    def clean(self):
        from django.core.exceptions import ValidationError
        from .sms_automation import validate_template

        validate_template(self.text)
        if self.event == self.Event.TRIAL and self.trial_day not in range(1, 8):
            raise ValidationError({"trial_day": "Trial day must be between 1 and 7."})
        if self.event != self.Event.TRIAL and self.trial_day is not None:
            raise ValidationError({"trial_day": "Only trial messages have a day."})
        if self.delay_minutes > 10080 or (self.event == self.Event.TRIAL and self.delay_minutes):
            raise ValidationError({"delay_minutes": "Invalid event delay."})


class SMSBroadcast(models.Model):
    """Immutable administrator-approved audience snapshot."""

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    idempotency_key = models.CharField(max_length=64, unique=True)
    membership_tiers = models.JSONField(default=list)
    market = models.CharField(max_length=12, default="ALL")
    text = models.CharField(max_length=500)
    recipient_count = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)


class SMSAutomationDelivery(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SENDING = "SENDING", "Sending / reconciliation required if interrupted"
        SENT = "SENT", "Sent"
        FAILED = "FAILED", "Failed"
        SKIPPED = "SKIPPED", "Skipped after eligibility changed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    rule = models.ForeignKey(SMSAutomationRule, on_delete=models.SET_NULL, null=True, blank=True)
    broadcast = models.ForeignKey(SMSBroadcast, on_delete=models.SET_NULL, null=True, blank=True)
    event_key = models.CharField(max_length=100)
    event = models.CharField(max_length=20)
    phone = models.CharField(max_length=20)
    text = models.CharField(max_length=500)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    scheduled_at = models.DateTimeField()
    claimed_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    provider_message_id = models.CharField(max_length=100, blank=True)
    failure_code = models.CharField(max_length=80, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [models.UniqueConstraint(
            fields=("user", "event_key"), name="unique_sms_automation_user_event"
        )]
        indexes = [
            models.Index(fields=("status", "scheduled_at"), name="sms_auto_status_due_idx"),
            models.Index(fields=("user", "-created_at"), name="sms_auto_user_time_idx"),
        ]
