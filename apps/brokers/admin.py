from django.contrib import admin

from .models import Broker


@admin.register(Broker)
class BrokerAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "country",
        "rating",
        "minimum_deposit",
        "is_active",
        "sort_order",
        "created_at",
    )

    list_filter = (
        "is_active",
        "country",
        "rating",
    )

    search_fields = (
        "name",
        "short_description",
        "description",
        "country",
        "regulation",
    )

    ordering = (
        "sort_order",
        "-rating",
        "name",
    )

    readonly_fields = (
        "slug",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            "Basic information",
            {
                "fields": (
                    "name",
                    "slug",
                    "short_description",
                    "description",
                    "logo",
                ),
            },
        ),
        (
            "Broker links",
            {
                "fields": (
                    "website_url",
                    "registration_url",
                    "support_url",
                ),
            },
        ),
        (
            "Trading information",
            {
                "fields": (
                    "country",
                    "regulation",
                    "minimum_deposit",
                    "rating",
                    "features",
                ),
            },
        ),
        (
            "Display settings",
            {
                "fields": (
                    "is_active",
                    "sort_order",
                ),
            },
        ),
        (
            "Dates",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )