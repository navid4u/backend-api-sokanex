from django.conf import settings
from django.db import models
from django.utils.text import slugify


class VideoCategory(models.Model):

    name = models.CharField(
        max_length=100,
        unique=True,
    )

    slug = models.SlugField(
        max_length=120,
        unique=True,
        allow_unicode=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Video categories"

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(
                self.name,
                allow_unicode=True,
            ) or "video-category"

            slug = base_slug
            counter = 2

            while VideoCategory.objects.filter(
                slug=slug
            ).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            self.slug = slug

        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Video(models.Model):

    class SourceType(models.TextChoices):
        UPLOAD = "UPLOAD", "Uploaded file"
        EXTERNAL = "EXTERNAL", "External URL"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PUBLISHED = "PUBLISHED", "Published"

    title = models.CharField(
        max_length=250,
    )

    slug = models.SlugField(
        max_length=280,
        unique=True,
        allow_unicode=True,
        blank=True,
    )

    summary = models.TextField(
        blank=True,
    )

    source_type = models.CharField(
        max_length=10,
        choices=SourceType.choices,
    )

    video_file = models.FileField(
        upload_to="videos/",
        null=True,
        blank=True,
    )

    external_url = models.URLField(
        max_length=500,
        blank=True,
    )

    thumbnail = models.ImageField(
        upload_to="videos/thumbnails/",
        null=True,
        blank=True,
    )

    duration_seconds = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    category = models.ForeignKey(
        VideoCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="videos",
    )

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="videos",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    published_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "-published_at",
            "-created_at",
        ]

        indexes = [
            models.Index(
                fields=["status", "-published_at"]
            ),
            models.Index(
                fields=["category", "status"]
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(
                self.title,
                allow_unicode=True,
            ) or "video"

            slug = base_slug
            counter = 2

            while Video.objects.filter(
                slug=slug
            ).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            self.slug = slug

        super().save(*args, **kwargs)

    def __str__(self):
        return self.title