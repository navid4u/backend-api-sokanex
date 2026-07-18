from django.contrib import admin
from .models import Signal


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
    )

    search_fields = (
        "title",
        "symbol",
    )