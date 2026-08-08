from django.conf import settings
from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
from django.utils.text import slugify
from datetime import timedelta
from common.content_access import LevelRestrictedContent


class LiveEvent(LevelRestrictedContent):

    class Status(models.TextChoices):
        SCHEDULED = "SCHEDULED", "Scheduled"
        LIVE = "LIVE", "Live"
        ENDED = "ENDED", "Ended"
        CANCELLED = "CANCELLED", "Cancelled"
        DISABLED = "DISABLED", "Disabled"

    title = models.CharField(
        max_length=250,
    )

    slug = models.SlugField(
        max_length=280,
        unique=True,
        allow_unicode=True,
        blank=True,
    )

    description = models.TextField(
        blank=True,
    )

    thumbnail = models.ImageField(
        upload_to="livestream/thumbnails/",
        null=True,
        blank=True,
    )

    stream_url = models.URLField(
        max_length=500,
        blank=True,
    )

    replay_url = models.URLField(
        max_length=500,
        blank=True,
    )
    provider_join_url = models.URLField(max_length=500, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    room_name = models.CharField(max_length=255, unique=True, null=True, blank=True)
    max_participants = models.PositiveIntegerField(
        default=50, validators=[MinValueValidator(1), MaxValueValidator(10000)]
    )
    viewer_display_offset = models.PositiveIntegerField(
        default=0, validators=[MaxValueValidator(1000000)]
    )
    comments_enabled = models.BooleanField(default=True)
    recording_enabled = models.BooleanField(default=True)

    starts_at = models.DateTimeField()

    ends_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SCHEDULED,
    )

    host = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hosted_live_events",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_live_events",
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
        ordering = ["starts_at"]

        indexes = [
            models.Index(
                fields=[
                    "status",
                    "starts_at",
                ]
            ),
            models.Index(
                fields=[
                    "is_active",
                    "starts_at",
                ]
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(
                self.title,
                allow_unicode=True,
            ) or "live-event"

            slug = base_slug
            counter = 2

            while LiveEvent.objects.filter(
                slug=slug
            ).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            self.slug = slug

        if not self.room_name and self.slug:
            self.room_name = f"sokanex-live-{self.slug}"[:255]

        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

    @property
    def viewer_count(self) -> int:
        from django.utils import timezone
        return self.presences.filter(left_at__isnull=True, last_seen_at__gte=timezone.now() - timedelta(minutes=2)).count()

    @property
    def display_viewer_count(self) -> int:
        return self.viewer_count + self.viewer_display_offset


class LivePresence(models.Model):
    event = models.ForeignKey(LiveEvent, on_delete=models.CASCADE, related_name="presences")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="live_presences")
    joined_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    left_at = models.DateTimeField(null=True, blank=True)
    is_muted = models.BooleanField(default=False)
    can_publish = models.BooleanField(default=False)
    removed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="removed_live_participants",
    )

    class Meta:
        constraints = [models.UniqueConstraint(fields=["event", "user"], name="unique_live_presence")]


class SpeakRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    event = models.ForeignKey(LiveEvent, on_delete=models.CASCADE, related_name="speak_requests")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="live_speak_requests")
    message = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [models.UniqueConstraint(fields=["event", "user", "status"], name="unique_live_speak_request_status")]


class LiveChatMessage(models.Model):
    event = models.ForeignKey(LiveEvent, on_delete=models.CASCADE, related_name="chat_messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="live_chat_messages")
    text = models.CharField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="deleted_live_chat_messages",
    )

    class Meta:
        ordering = ["-created_at", "-id"]


class LiveRecording(models.Model):
    class Status(models.TextChoices):
        STARTING = "starting", "Starting"
        ACTIVE = "active", "Active"
        ENDING = "ending", "Ending"
        COMPLETE = "complete", "Complete"
        FAILED = "failed", "Failed"

    event = models.ForeignKey(LiveEvent, on_delete=models.CASCADE, related_name="recordings")
    egress_id = models.CharField(max_length=150, unique=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.STARTING)
    file_path = models.CharField(max_length=1000, blank=True)
    playback_url = models.URLField(max_length=1000, blank=True)
    error = models.CharField(max_length=1000, blank=True)
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="started_live_recordings",
    )
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-started_at", "-id"]
