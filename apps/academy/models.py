from django.conf import settings
from django.db import models
from django.utils.text import slugify

from common.content_access import LevelRestrictedContent


def default_playback_speeds():
    return [0.75, 1, 1.25, 1.5, 2]


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
    is_free = models.BooleanField(default=True)
    price = models.PositiveBigIntegerField(default=0)
    currency = models.CharField(max_length=3, default="IRT")
    purchase_required = models.BooleanField(default=False)
    weekly_session_limit = models.PositiveIntegerField(null=True, blank=True)
    monthly_session_limit = models.PositiveIntegerField(null=True, blank=True)
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
    class MediaType(models.TextChoices):
        VIDEO = "video", "Video"
        AUDIO = "audio", "Audio"
        TEXT = "text", "Text"
        LIVE = "live", "Live"

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
    media_type = models.CharField(max_length=10, choices=MediaType.choices, default=MediaType.VIDEO)
    audio_file = models.FileField(upload_to="academy/sessions/audio/%Y/%m/", null=True, blank=True)
    cover = models.ImageField(upload_to="academy/sessions/covers/%Y/%m/", null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    playback_speeds = models.JSONField(default=default_playback_speeds, blank=True)
    unlock_at = models.DateTimeField(null=True, blank=True)
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


class CoursePurchase(models.Model):
    class Method(models.TextChoices):
        WALLET = "WALLET", "Wallet"
        GATEWAY = "GATEWAY", "Gateway"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="course_purchases")
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="purchases")
    amount_irt = models.PositiveBigIntegerField()
    payment_method = models.CharField(max_length=10, choices=Method.choices)
    ledger_transaction = models.ForeignKey("wallet.LedgerTransaction", null=True, blank=True, on_delete=models.PROTECT)
    payment = models.OneToOneField("wallet.Payment", null=True, blank=True, on_delete=models.PROTECT, related_name="course_purchase")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "course"], name="unique_course_purchase")]


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


class Quiz(models.Model):
    session = models.OneToOneField(CourseSession, on_delete=models.CASCADE, related_name="quiz")
    title = models.CharField(max_length=250)
    required_score = models.PositiveSmallIntegerField(default=70)
    max_attempts = models.PositiveSmallIntegerField(default=3)
    retry_delay_minutes = models.PositiveIntegerField(default=60)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class QuizQuestion(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="questions")
    text = models.TextField()
    order = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["order", "id"]


class QuizOption(models.Model):
    question = models.ForeignKey(QuizQuestion, on_delete=models.CASCADE, related_name="options")
    text = models.CharField(max_length=500)
    is_correct = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["order", "id"]


class QuizAttempt(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="attempts")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="quiz_attempts")
    answers = models.JSONField(default=dict)
    score = models.DecimalField(max_digits=5, decimal_places=2)
    passed = models.BooleanField(default=False)
    attempt_number = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    next_attempt_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["quiz", "user", "attempt_number"], name="unique_quiz_attempt_number")]
