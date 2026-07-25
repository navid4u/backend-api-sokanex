from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.db.models import Q


class User(AbstractUser):

    class Role(models.TextChoices):
        SUPER_ADMIN = "SUPER_ADMIN", "Super Admin"
        ADMIN = "ADMIN", "Admin"
        TRADER = "TRADER", "Trader"
        EMPLOYEE = "EMPLOYEE", "Employee"
        USER = "USER", "User"

    class AccessLevel(models.IntegerChoices):
        LEVEL_1 = 1, "Level 1"
        LEVEL_2 = 2, "Level 2"
        LEVEL_3 = 3, "Level 3"
        LEVEL_4 = 4, "Level 4"
        LEVEL_5 = 5, "Level 5"

    phone = models.CharField(
        max_length=20,
        unique=True,
        null=True,
        blank=True
    )

    avatar = models.ImageField(
        upload_to="avatars/",
        null=True,
        blank=True
    )

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.USER
    )

    access_level = models.PositiveSmallIntegerField(
        default=AccessLevel.LEVEL_1,
        choices=AccessLevel.choices,
    )

    is_verified = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.username


class UpgradeRequest(models.Model):

    class Type(models.TextChoices):
        UPGRADE = "UPGRADE", "Level upgrade"
        PREMIUM = "PREMIUM", "Premium subscription"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="upgrade_requests",
    )
    request_type = models.CharField(
        max_length=20,
        choices=Type.choices,
        default=Type.UPGRADE,
    )
    requested_level = models.PositiveSmallIntegerField(
        choices=[(level, f"Level {level}") for level in range(2, 6)],
    )
    message = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    admin_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_upgrade_requests",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(status="PENDING"),
                name="one_pending_upgrade_request_per_user",
            ),
        ]

    def __str__(self):
        return (
            f"{self.user} - {self.request_type} "
            f"to level {self.requested_level}"
        )
