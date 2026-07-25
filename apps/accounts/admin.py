from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import PlatformRole, UpgradeRequest, User, UserProfile


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    extra = 0
    can_delete = False
    classes = ("collapse",)


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    inlines = (UserProfileInline,)
    list_display = (
        "id",
        "username",
        "email",
        "role",
        "access_level",
        "custom_role",
        "is_verified",
        "is_active",
        "is_staff",
        "date_joined",
    )

    list_filter = (
        "role",
        "access_level",
        "custom_role",
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
                    "custom_role",
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
                    "custom_role",
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


@admin.register(PlatformRole)
class PlatformRoleAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "slug", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug", "description")
    readonly_fields = ("created_at", "updated_at")


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "country",
        "city",
        "occupation",
        "monthly_income_range",
        "risk_tolerance",
        "updated_at",
    )
    list_filter = (
        "gender",
        "marital_status",
        "education_level",
        "monthly_income_range",
        "risk_tolerance",
        "trading_frequency",
    )
    search_fields = (
        "user__username",
        "user__email",
        "country",
        "city",
        "occupation",
        "job_title",
    )
    readonly_fields = ("created_at", "updated_at")
