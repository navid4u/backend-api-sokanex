from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import UpgradeRequest, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = (
        "id",
        "username",
        "email",
        "role",
        "access_level",
        "is_verified",
        "is_active",
        "is_staff",
        "date_joined",
    )

    list_filter = (
        "role",
        "access_level",
        "is_verified",
        "is_active",
        "is_staff",
        "is_superuser",
    )

    search_fields = (
        "username",
        "email",
        "first_name",
        "last_name",
        "phone",
    )

    ordering = (
        "-date_joined",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
        "last_login",
        "date_joined",
    )

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "username",
                    "password",
                ),
            },
        ),
        (
            "Personal information",
            {
                "fields": (
                    "first_name",
                    "last_name",
                    "email",
                    "phone",
                    "avatar",
                ),
            },
        ),
        (
            "Platform access",
            {
                "fields": (
                    "role",
                    "access_level",
                    "is_verified",
                    "is_active",
                ),
            },
        ),
        (
            "Django administration",
            {
                "fields": (
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (
            "Important dates",
            {
                "fields": (
                    "last_login",
                    "date_joined",
                    "created_at",
                    "updated_at",
                ),
                "classes": (
                    "collapse",
                ),
            },
        ),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": (
                    "wide",
                ),
                "fields": (
                    "username",
                    "email",
                    "phone",
                    "role",
                    "access_level",
                    "password1",
                    "password2",
                    "is_active",
                    "is_verified",
                    "is_staff",
                ),
            },
        ),
    )


@admin.register(UpgradeRequest)
class UpgradeRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "request_type",
        "requested_level",
        "status",
        "reviewed_by",
        "created_at",
    )
    list_filter = ("status", "request_type", "requested_level")
    search_fields = ("user__username", "user__email", "message")
    readonly_fields = ("created_at", "updated_at", "reviewed_at")
