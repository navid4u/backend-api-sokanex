from django.contrib import admin

from .models import Course, CourseSession


class CourseSessionInline(admin.TabularInline):
    model = CourseSession
    extra = 0
    ordering = ("order",)


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "instructor",
        "status",
        "created_at",
    )
    list_filter = (
        "status",
        "allowed_level_1",
        "allowed_level_2",
        "allowed_level_3",
        "allowed_level_4",
        "allowed_level_5",
    )
    search_fields = (
        "title",
        "description",
        "instructor__username",
    )
    readonly_fields = ("created_at", "updated_at")
    inlines = (CourseSessionInline,)


@admin.register(CourseSession)
class CourseSessionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "course",
        "order",
        "title",
        "is_published",
    )
    list_filter = ("is_published",)
    search_fields = ("title", "text", "course__title")
    ordering = ("course", "order")
