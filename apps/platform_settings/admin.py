from django.contrib import admin

from .models import PlatformSettings, SystemContent, UITranslationAuditLog, UITranslationCatalog


@admin.register(PlatformSettings)
class PlatformSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "site_name",
        "minimum_deposit_irt",
        "minimum_withdrawal_irt",
        "maximum_withdrawal_irt",
        "updated_at",
    )

    def has_add_permission(self, request):
        return not PlatformSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SystemContent)
class SystemContentAdmin(admin.ModelAdmin):
    list_display = ("key", "section", "label", "multiline", "updated_at")
    list_filter = ("section", "multiline")
    search_fields = ("key", "label", "value")
    readonly_fields = ("key", "section", "label", "multiline", "updated_at")


@admin.register(UITranslationCatalog)
class UITranslationCatalogAdmin(admin.ModelAdmin):
    list_display = ("locale", "version", "updated_by", "updated_at")
    readonly_fields = tuple(field.name for field in UITranslationCatalog._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(UITranslationAuditLog)
class UITranslationAuditLogAdmin(admin.ModelAdmin):
    list_display = ("catalog", "actor", "previous_version", "new_version", "created_at")
    readonly_fields = tuple(field.name for field in UITranslationAuditLog._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
