from django.conf import settings
from django.db import models
from uuid import uuid4
from pathlib import Path


def secure_channel_upload(instance, filename):
    extension = Path(filename).suffix.lower()
    return f"channels/uploads/{uuid4().hex}{extension}"


class Channel(models.Model):
    slug = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=150)
    min_access_level = models.PositiveSmallIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class ChannelMembership(models.Model):
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="channel_memberships")
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["channel", "user"], name="unique_channel_membership")]


class ChannelPost(models.Model):
    class Scope(models.TextChoices):
        DOLLAR = "DOLLAR", "دلار"
        GOLD = "GOLD", "طلا"
        STOCK = "STOCK", "بورس"
        HOUSING = "HOUSING", "مسکن"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "پیش‌نویس"
        SCHEDULED = "SCHEDULED", "زمان‌بندی‌شده"
        PUBLISHED = "PUBLISHED", "منتشرشده"

    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name="posts")
    title = models.CharField(max_length=250)
    body = models.TextField()
    image = models.ImageField(upload_to=secure_channel_upload, null=True, blank=True)
    video = models.FileField(upload_to=secure_channel_upload, null=True, blank=True)
    audio = models.FileField(upload_to=secure_channel_upload, null=True, blank=True)
    cover = models.ImageField(upload_to=secure_channel_upload, null=True, blank=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="channel_posts")
    signal = models.ForeignKey("signals.Signal", on_delete=models.SET_NULL, null=True, blank=True, related_name="channel_posts")
    scope = models.CharField(max_length=20, choices=Scope.choices, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PUBLISHED, db_index=True)
    is_pinned = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    views_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_pinned", "-published_at", "-id"]
