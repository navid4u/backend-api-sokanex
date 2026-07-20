from django.contrib import admin
from django.utils import timezone

from .models import LiveEvent


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
        "mark_as_live",
        "mark_as_ended",
        "mark_as_cancelled",
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

    @admin.action(
        description="Mark selected events as live"
    )
    def mark_as_live(
        self,
        request,
        queryset,
    ):
        updated = queryset.update(
            status=LiveEvent.Status.LIVE,
            is_active=True,
        )

        self.message_user(
            request,
            f"{updated} event(s) marked as live.",
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
            ends_at=timezone.now(),
        )

        self.message_user(
            request,
            f"{updated} event(s) marked as ended.",
        )

    @admin.action(
        description="Cancel selected events"
    )
    def mark_as_cancelled(
        self,
        request,
        queryset,
    ):
        updated = queryset.update(
            status=LiveEvent.Status.CANCELLED,
        )

        self.message_user(
            request,
            f"{updated} event(s) cancelled.",
        )