from django.contrib import admin

from .models import LandingPage, LandingSection


class LandingSectionInline(admin.StackedInline):
    model = LandingSection
    extra = 0
    ordering = ("display_order", "id")


@admin.register(LandingPage)
class LandingPageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "site_key",
        "site_name",
        "is_active",
        "updated_at",
    )
    list_filter = ("is_active",)
    search_fields = ("site_key", "site_name", "page_title")
    readonly_fields = ("created_at", "updated_at")
    inlines = (LandingSectionInline,)


@admin.register(LandingSection)
class LandingSectionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "key",
        "section_type",
        "page",
        "display_order",
        "is_active",
    )
    list_filter = ("page", "section_type", "is_active")
    search_fields = ("key", "title", "subtitle")
    ordering = ("page", "display_order", "id")
    readonly_fields = ("created_by", "created_at", "updated_at")
