from django.contrib import admin
from django.utils import timezone
from django import forms

from .models import AlocomSettings, LiveEvent


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


class AlocomSettingsAdminForm(forms.ModelForm):
    api_token = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Leave blank to keep the currently stored encrypted token.",
    )

    class Meta:
        model = AlocomSettings
        fields = ("api_base_url", "api_token", "enabled", "request_timeout_seconds", "verify_ssl")


@admin.register(AlocomSettings)
class AlocomSettingsAdmin(admin.ModelAdmin):
    form = AlocomSettingsAdminForm
    list_display = ("api_base_url", "enabled", "request_timeout_seconds", "updated_at")
    readonly_fields = ("updated_at", "updated_by")

    def save_model(self, request, obj, form, change):
        token = form.cleaned_data.get("api_token")
        if token:
            obj.set_api_token(token)
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

    def has_add_permission(self, request):
        return not AlocomSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
