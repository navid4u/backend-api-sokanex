from django.contrib import admin

from .models import (
    ChatRoom, Message, PostComment, PostReaction, PostReport,
    RoomMembership, SavedPost, SupportMessage, SupportThread, TraderPost, UserFollow,
)


class RoomMembershipInline(admin.TabularInline):
    model = RoomMembership
    extra = 0
    autocomplete_fields = (
        "user",
    )


@admin.register(ChatRoom)
class ChatRoomAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "is_public",
        "is_active",
        "created_by",
        "created_at",
    )
    list_filter = (
        "is_public",
        "is_active",
        "created_at",
    )
    search_fields = (
        "name",
        "slug",
        "description",
        "created_by__username",
    )
    list_select_related = (
        "created_by",
    )
    readonly_fields = (
        "created_by",
        "created_at",
        "updated_at",
    )
    inlines = (
        RoomMembershipInline,
    )

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(RoomMembership)
class RoomMembershipAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "room",
        "user",
        "role",
        "joined_at",
    )
    list_filter = (
        "role",
        "room",
        "joined_at",
    )
    search_fields = (
        "room__name",
        "user__username",
        "user__email",
    )
    list_select_related = (
        "room",
        "user",
    )
    autocomplete_fields = (
        "room",
        "user",
    )
    readonly_fields = (
        "joined_at",
    )


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "room",
        "sender",
        "short_text",
        "is_deleted",
        "created_at",
    )
    list_filter = (
        "room",
        "is_deleted",
        "created_at",
    )
    search_fields = (
        "text",
        "room__name",
        "sender__username",
    )
    list_select_related = (
        "room",
        "sender",
        "reply_to",
    )
    autocomplete_fields = (
        "room",
        "sender",
        "reply_to",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
    )
    ordering = (
        "-created_at",
    )
    date_hierarchy = "created_at"

    @admin.display(description="Message")
    def short_text(self, obj):
        if obj.is_deleted:
            return "[deleted]"
        return obj.text[:80]


@admin.register(TraderPost)
class TraderPostAdmin(admin.ModelAdmin):
    list_display = ("id", "author", "visibility", "is_deleted", "created_at")
    list_filter = ("visibility", "is_deleted", "created_at")
    search_fields = ("author__username", "text")


@admin.register(PostComment)
class PostCommentAdmin(admin.ModelAdmin):
    list_display = ("id", "post", "author", "is_deleted", "created_at")
    list_filter = ("is_deleted", "created_at")
    search_fields = ("author__username", "text")


@admin.register(PostReport)
class PostReportAdmin(admin.ModelAdmin):
    list_display = ("id", "post", "reporter", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("reporter__username", "reason")


admin.site.register(PostReaction)
admin.site.register(SavedPost)
admin.site.register(UserFollow)


class SupportMessageInline(admin.TabularInline):
    model = SupportMessage
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(SupportThread)
class SupportThreadAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "assigned_to", "status", "priority", "last_message_at")
    search_fields = ("user__username", "user__first_name", "user__last_name", "user__phone", "subject")
    list_filter = ("status", "priority")
    readonly_fields = ("last_message_at", "closed_at", "created_at", "updated_at")
    inlines = (SupportMessageInline,)
