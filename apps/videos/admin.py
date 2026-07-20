from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import Video, VideoCategory


class VideoAdminForm(forms.ModelForm):
    class Meta:
        model = Video
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()
        source_type = cleaned_data.get("source_type")
        video_file = cleaned_data.get("video_file")
        external_url = cleaned_data.get("external_url")

        if source_type == Video.SourceType.UPLOAD and not video_file:
            raise ValidationError(
                "An uploaded video file is required for UPLOAD source type."
            )

        if source_type == Video.SourceType.EXTERNAL and not external_url:
            raise ValidationError(
                "An external URL is required for EXTERNAL source type."
            )

        return cleaned_data


@admin.register(VideoCategory)
class VideoCategoryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "slug",
        "created_at",
    )
    search_fields = (
        "name",
        "slug",
    )
    ordering = (
        "name",
    )
    readonly_fields = (
        "created_at",
    )


@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    form = VideoAdminForm

    list_display = (
        "id",
        "title",
        "category",
        "source_type",
        "status",
        "author",
        "published_at",
    )
    list_filter = (
        "status",
        "source_type",
        "category",
        "published_at",
    )
    search_fields = (
        "title",
        "slug",
        "summary",
        "author__username",
    )
    list_select_related = (
        "category",
        "author",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
    )
    ordering = (
        "-published_at",
        "-created_at",
    )
    date_hierarchy = "published_at"
    actions = (
        "publish_videos",
        "move_to_draft",
    )

    def save_model(self, request, obj, form, change):
        if not obj.author_id:
            obj.author = request.user

        if obj.status == Video.Status.PUBLISHED and obj.published_at is None:
            obj.published_at = timezone.now()

        if obj.status == Video.Status.DRAFT:
            obj.published_at = None

        super().save_model(request, obj, form, change)

    @admin.action(description="Publish selected videos")
    def publish_videos(self, request, queryset):
        updated = queryset.update(
            status=Video.Status.PUBLISHED,
            published_at=timezone.now(),
        )
        self.message_user(request, f"{updated} video(s) published.")

    @admin.action(description="Move selected videos to draft")
    def move_to_draft(self, request, queryset):
        updated = queryset.update(
            status=Video.Status.DRAFT,
            published_at=None,
        )
        self.message_user(request, f"{updated} video(s) moved to draft.")
