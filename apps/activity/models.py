from django.conf import settings
from django.db import models
import uuid


class UserActivity(models.Model):
    class Type(models.TextChoices):
        REGISTER = "REGISTER", "Registration"
        LOGIN = "LOGIN", "Login"
        LOGOUT = "LOGOUT", "Logout"
        PROFILE_UPDATE = "PROFILE_UPDATE", "Profile updated"
        ARTICLE_READ = "ARTICLE_READ", "Article read"
        VIDEO_WATCH = "VIDEO_WATCH", "Video watched"
        LIVE_JOIN = "LIVE_JOIN", "Live joined"
        COURSE_VIEW = "COURSE_VIEW", "Course viewed"
        COURSE_SESSION_VIEW = "COURSE_SESSION_VIEW", "Course session viewed"
        CREATE = "CREATE", "Content created"
        UPDATE = "UPDATE", "Content updated"
        DELETE = "DELETE", "Content deleted"
        SOCIAL = "SOCIAL", "Social activity"
        SECURITY = "SECURITY", "Security activity"
        PERSONALITY_TEST_COMPLETED = "PERSONALITY_TEST_COMPLETED", "Personality test completed"
        MARKET_ACCESS_REQUEST = "MARKET_ACCESS_REQUEST", "Market access requested"
        MARKET_PREFERENCES_UPDATE = "MARKET_PREFERENCES_UPDATE", "Market preferences updated"
        COURSE_ENROLL = "COURSE_ENROLL", "Course enrolled"
        ASSET_ADDED = "ASSET_ADDED", "Asset holding added"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="recent_activities",
    )
    activity_type = models.CharField(max_length=30, choices=Type.choices)
    title = models.CharField(max_length=200)
    description = models.CharField(max_length=500, blank=True)
    target_type = models.CharField(max_length=80, blank=True)
    target_id = models.CharField(max_length=80, blank=True)
    target_url = models.CharField(max_length=500, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["-created_at", "-id"], name="activity_recent_global_idx"),
        ]

    def __str__(self):
        return f"{self.user}: {self.title}"


class PageViewEvent(models.Model):
    """Short-lived, authenticated canonical-route event; no browser fingerprint."""

    event_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    session_id = models.UUIDField()
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    path = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    aggregated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["created_at", "path"]),
            models.Index(fields=["user", "created_at"], name="activity_pv_user_time_idx"),
        ]


class PageViewDailyAggregate(models.Model):
    """Per-user Tehran-day rollup preserves exact distinct-user counts after raw expiry."""

    day = models.DateField(db_index=True)
    path = models.CharField(max_length=64)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    views = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["day", "path", "user"], name="activity_page_view_day_path_user_uniq")]
        indexes = [models.Index(fields=["day", "path"]), models.Index(fields=["day", "user"])]


class PageViewReceipt(models.Model):
    """Small dedupe ledger outliving raw events; stores no session or URL."""

    event_id = models.UUIDField(primary_key=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

