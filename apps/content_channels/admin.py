from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html
from .models import Channel, ChannelMembership, ChannelPost

admin.site.register(Channel)
admin.site.register(ChannelMembership)

@admin.register(ChannelPost)
class ChannelPostAdmin(admin.ModelAdmin):
    list_display = ("title", "scope", "status", "is_pinned", "author", "published_at", "views_count")
    list_filter = ("scope", "status", "is_pinned")
    search_fields = ("title", "body", "author__username", "author__first_name", "author__last_name")
    readonly_fields = ("image_preview", "cover_preview", "views_count", "created_at", "updated_at")
    actions = ("publish_posts", "draft_posts", "pin_posts", "unpin_posts")

    @admin.display(description="Image preview")
    def image_preview(self, obj):
        return format_html('<img src="{}" style="max-width:320px;max-height:180px" />', obj.image.url) if obj.image else "-"

    @admin.display(description="Cover preview")
    def cover_preview(self, obj):
        return format_html('<img src="{}" style="max-width:320px;max-height:180px" />', obj.cover.url) if obj.cover else "-"

    @admin.action(description="Publish selected posts")
    def publish_posts(self, request, queryset):
        queryset.update(status=ChannelPost.Status.PUBLISHED, published_at=timezone.now())

    @admin.action(description="Move selected posts to draft")
    def draft_posts(self, request, queryset):
        queryset.update(status=ChannelPost.Status.DRAFT)

    @admin.action(description="Pin selected posts")
    def pin_posts(self, request, queryset):
        queryset.update(is_pinned=True)

    @admin.action(description="Unpin selected posts")
    def unpin_posts(self, request, queryset):
        queryset.update(is_pinned=False)
