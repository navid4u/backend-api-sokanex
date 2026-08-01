from django.conf import settings
from django.db import models
from django.utils.text import slugify

from common.content_access import LevelRestrictedContent


class Course(LevelRestrictedContent):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PUBLISHED = "PUBLISHED", "Published"

    title = models.CharField(max_length=250)
    slug = models.SlugField(
        max_length=280,
        unique=True,
        allow_unicode=True,
        blank=True,
    )
    description = models.TextField(blank=True)
    short_description = models.CharField(max_length=500, blank=True)
    cover_image = models.ImageField(
        upload_to="academy/courses/",
        null=True,
        blank=True,
    )
    instructor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="academy_courses",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    difficulty = models.CharField(
        max_length=20,
        choices=(("BEGINNER", "Beginner"), ("INTERMEDIATE", "Intermediate"), ("ADVANCED", "Advanced")),
        default="BEGINNER",
    )
    trailer_url = models.URLField(max_length=500, blank=True)
    estimated_duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    prerequisites = models.JSONField(default=list, blank=True)
    learning_outcomes = models.JSONField(default=list, blank=True)
    enrollment_open = models.BooleanField(default=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["instructor", "status"]),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(
                self.title,
                allow_unicode=True,
            ) or "course"
            slug = base_slug
            counter = 2
            while Course.objects.filter(slug=slug).exclude(
                pk=self.pk
            ).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class CourseSession(models.Model):
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="sessions",
    )
    title = models.CharField(max_length=250)
    order = models.PositiveIntegerField()
    video_url = models.URLField(max_length=500, blank=True)
    video_file = models.FileField(
        upload_to="academy/sessions/videos/%Y/%m/", null=True, blank=True
    )
    duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    text = models.TextField(blank=True)
    image = models.ImageField(
        upload_to="academy/sessions/",
        null=True,
        blank=True,
    )
    is_published = models.BooleanField(default=True)
    is_preview = models.BooleanField(default=False)
    available_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["course", "order"],
                name="unique_session_order_per_course",
            )
        ]

    def __str__(self):
        return f"{self.course} - {self.order}. {self.title}"


class CourseEnrollment(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="course_enrollments"
    )
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="enrollments")
    enrolled_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "course"], name="unique_course_enrollment")
        ]
        ordering = ["-enrolled_at"]


class SessionProgress(models.Model):
    enrollment = models.ForeignKey(
        CourseEnrollment, on_delete=models.CASCADE, related_name="session_progress"
    )
    session = models.ForeignKey(
        CourseSession, on_delete=models.CASCADE, related_name="progress_records"
    )
    progress_percent = models.PositiveSmallIntegerField(default=0)
    last_position_seconds = models.PositiveIntegerField(default=0)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["enrollment", "session"], name="unique_session_progress")
        ]
