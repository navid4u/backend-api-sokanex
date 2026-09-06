from django.contrib import admin

from .models import LogEvent


@admin.register(LogEvent)
class LogEventAdmin(admin.ModelAdmin):
    list_display = ("id", "created_at", "source", "level", "category", "status_code", "path", "is_resolved")
    list_filter = ("source", "level", "category", "is_resolved", "created_at")
    search_fields = ("message", "path", "error_type", "request_id", "user__username")
    readonly_fields = tuple(field.name for field in LogEvent._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
