from django.contrib import admin

from .models import LiveChatMessage, LiveEvent, LivePresence, SpeakRequest

admin.site.register(LivePresence)
admin.site.register(SpeakRequest)
admin.site.register(LiveChatMessage)


@admin.register(LiveEvent)
class LiveEventAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "status",
        "host",
        "starts_at",
        "ends_at",
        "is_active",
    )

    list_filter = (
        "status",
        "is_active",
        "starts_at",
        "allowed_level_1",
        "allowed_level_2",
        "allowed_level_3",
        "allowed_level_4",
        "allowed_level_5",
    )

    search_fields = (
        "title",
        "slug",
        "description",
        "host__username",
    )

    list_select_related = (
        "host",
        "created_by",
    )

    readonly_fields = (
        "created_by",
        "created_at",
        "updated_at",
    )

    ordering = (
        "starts_at",
    )

    date_hierarchy = "starts_at"

    actions = (
        "mark_as_active",
        "mark_as_ended",
        "mark_as_upcoming",
        "mark_as_within_hour",
    )

    def save_model(
        self,
        request,
        obj,
        form,
        change,
    ):
        if not obj.created_by_id:
            obj.created_by = request.user

        super().save_model(
            request,
            obj,
            form,
            change,
        )

    @admin.action(description="Mark selected events as active")
    def mark_as_active(
        self,
        request,
        queryset,
    ):
        updated = queryset.update(
            status=LiveEvent.Status.ACTIVE,
            is_active=True,
        )

        self.message_user(
            request,
            f"{updated} event(s) marked as active.",
        )

    @admin.action(
        description="Mark selected events as ended"
    )
    def mark_as_ended(
        self,
        request,
        queryset,
    ):
        updated = queryset.update(
            status=LiveEvent.Status.ENDED,
        )

        self.message_user(
            request,
            f"{updated} event(s) marked as ended.",
        )

    @admin.action(
        description="Mark selected events as upcoming"
    )
    def mark_as_upcoming(
        self,
        request,
        queryset,
    ):
        updated = queryset.update(
            status=LiveEvent.Status.UPCOMING,
            is_active=True,
        )

        self.message_user(
            request,
            f"{updated} event(s) marked as upcoming.",
        )

    @admin.action(description="Mark selected events as within one hour")
    def mark_as_within_hour(self, request, queryset):
        updated = queryset.update(
            status=LiveEvent.Status.WITHIN_HOUR,
            is_active=True,
        )
        self.message_user(request, f"{updated} event(s) marked as within one hour.")
