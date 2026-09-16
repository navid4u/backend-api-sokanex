from django.contrib import admin
from .models import Signal, SignalUpdate, VIPSignalPost

admin.site.register(SignalUpdate)


@admin.register(Signal)
class SignalAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "title",
        "symbol",
        "market",
        "direction",
        "status",
        "created_by",
        "created_at",
    )

    list_filter = (
        "status",
        "market",
        "direction",
        "allowed_level_1",
        "allowed_level_2",
        "allowed_level_3",
        "allowed_level_4",
        "allowed_level_5",
    )

    search_fields = (
        "title",
        "symbol",
    )


@admin.register(VIPSignalPost)
class VIPSignalPostAdmin(admin.ModelAdmin):
    list_display = ("id", "channel", "is_active", "published_at", "external_id")
    list_filter = ("channel", "is_active", "source")
    search_fields = ("text", "external_id")
    readonly_fields = ("source", "created_at", "updated_at")
