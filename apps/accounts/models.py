from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.db.models import Q
from django.utils.text import slugify


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

    class Permission(models.TextChoices):
        CONTENT_MANAGE = "CONTENT_MANAGE", "Manage content"
        CONTENT_VIEW_ALL = "CONTENT_VIEW_ALL", "View all content levels"
        SIGNAL_SUBMIT = "SIGNAL_SUBMIT", "Submit signals"
        SIGNAL_REVIEW = "SIGNAL_REVIEW", "Review signals"
        ACADEMY_TEACH = "ACADEMY_TEACH", "Create and teach courses"
        ACADEMY_MANAGE = "ACADEMY_MANAGE", "Manage all academy courses"
        USER_MANAGE = "USER_MANAGE", "Manage users"
        ROLE_MANAGE = "ROLE_MANAGE", "Manage custom roles"

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

    custom_role = models.ForeignKey(
        "PlatformRole",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
    )

    is_verified = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.username

    def has_platform_permission(self, permission):
        if self.is_superuser or self.role == self.Role.SUPER_ADMIN:
            return True

        system_permissions = {
            self.Role.ADMIN: {
                self.Permission.CONTENT_MANAGE,
                self.Permission.CONTENT_VIEW_ALL,
                self.Permission.SIGNAL_REVIEW,
                self.Permission.ACADEMY_MANAGE,
                self.Permission.USER_MANAGE,
                self.Permission.ROLE_MANAGE,
            },
            self.Role.EMPLOYEE: {
                self.Permission.CONTENT_MANAGE,
                self.Permission.CONTENT_VIEW_ALL,
                self.Permission.SIGNAL_REVIEW,
            },
            self.Role.TRADER: {
                self.Permission.SIGNAL_SUBMIT,
            },
        }

        if permission in system_permissions.get(self.role, set()):
            return True

        return bool(
            self.custom_role
            and self.custom_role.is_active
            and permission in self.custom_role.permissions
        )


class PlatformRole(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    permissions = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_platform_roles",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name, allow_unicode=True) or "role"
            slug = base_slug
            counter = 2
            while PlatformRole.objects.filter(slug=slug).exclude(
                pk=self.pk
            ).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)


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
