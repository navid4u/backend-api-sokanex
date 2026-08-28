from django.conf import settings
from django.db import models


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
        indexes = [models.Index(fields=["user", "-created_at"])]

    def __str__(self):
        return f"{self.user}: {self.title}"

