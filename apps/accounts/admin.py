from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    Badge, PlatformRole, SecuritySettings, UpgradeRequest,
    User, UserBadge, UserDevice, UserProfile, BrokerConnection,
)

admin.site.register(BrokerConnection)


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


@admin.register(UserDevice)
class UserDeviceAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "name", "ip_address", "last_seen_at", "revoked_at")
    list_filter = ("revoked_at", "created_at")
    search_fields = ("user__username", "device_id", "name", "ip_address")
    readonly_fields = ("device_id", "refresh_jti", "created_at", "last_seen_at")


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "slug", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "description")
    readonly_fields = ("created_at", "updated_at")


@admin.register(UserBadge)
class UserBadgeAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "badge", "awarded_by", "awarded_at")
    search_fields = ("user__username", "badge__name", "note")
    readonly_fields = ("awarded_at",)


@admin.register(SecuritySettings)
class SecuritySettingsAdmin(admin.ModelAdmin):
    list_display = ("id", "max_active_devices", "session_lifetime_days", "updated_at")
    readonly_fields = ("updated_at",)

    def has_add_permission(self, request):
        return not SecuritySettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
