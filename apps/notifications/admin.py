from django.contrib import admin

from .models import Notification, NotificationRead


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "notification_type",
        "recipient",
        "target_role",
        "is_active",
        "created_at",
    )
    list_filter = (
        "notification_type",
        "target_role",
        "is_active",
        "created_at",
    )
    search_fields = (
        "title",
        "message",
        "recipient__username",
        "recipient__email",
    )
    list_select_related = (
        "recipient",
        "created_by",
    )
    readonly_fields = (
        "created_by",
        "created_at",
        "updated_at",
    )
    ordering = (
        "-created_at",
    )
    date_hierarchy = "created_at"

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(NotificationRead)
class NotificationReadAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "notification",
        "user",
        "read_at",
    )
    list_filter = (
        "read_at",
    )
    search_fields = (
        "notification__title",
        "user__username",
        "user__email",
    )
    list_select_related = (
        "notification",
        "user",
    )
    readonly_fields = (
        "notification",
        "user",
        "read_at",
    )
    ordering = (
        "-read_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

