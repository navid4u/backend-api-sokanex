from django.contrib import admin

from .models import Course, CourseEnrollment, CourseSession, SessionProgress, Quiz, QuizAttempt, QuizOption, QuizQuestion

admin.site.register(Quiz)
admin.site.register(QuizQuestion)
admin.site.register(QuizOption)
admin.site.register(QuizAttempt)


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


@admin.register(CourseEnrollment)
class CourseEnrollmentAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "course", "enrolled_at", "completed_at")
    search_fields = ("user__username", "course__title")
    list_filter = ("enrolled_at", "completed_at")


@admin.register(SessionProgress)
class SessionProgressAdmin(admin.ModelAdmin):
    list_display = ("id", "enrollment", "session", "progress_percent", "updated_at")
    list_filter = ("progress_percent", "completed_at")
