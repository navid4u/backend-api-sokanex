from django.conf import settings
from django.db import models


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
        DOLLAR = "dollar", "Dollar"
        GOLD = "gold", "Gold"
        STOCK = "stock", "Stock"
        HOUSING = "housing", "Housing"

    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name="posts")
    title = models.CharField(max_length=250)
    body = models.TextField()
    image = models.ImageField(upload_to="channels/images/%Y/%m/", null=True, blank=True)
    video = models.FileField(upload_to="channels/videos/%Y/%m/", null=True, blank=True)
    audio = models.FileField(upload_to="channels/audio/%Y/%m/", null=True, blank=True)
    cover = models.ImageField(upload_to="channels/covers/%Y/%m/", null=True, blank=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="channel_posts")
    signal = models.ForeignKey("signals.Signal", on_delete=models.SET_NULL, null=True, blank=True, related_name="channel_posts")
    scope = models.CharField(max_length=20, choices=Scope.choices, blank=True)
    is_pinned = models.BooleanField(default=False)
    published_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_pinned", "-published_at", "-id"]
