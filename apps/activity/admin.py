from django.contrib import admin

from .models import UserActivity


@admin.register(UserActivity)
class UserActivityAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "activity_type", "title", "created_at")
    list_filter = ("activity_type", "created_at")
    search_fields = ("user__username", "title", "description")
    readonly_fields = ("created_at",)

