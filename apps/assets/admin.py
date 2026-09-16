from django.contrib import admin

from .models import AssetCatalogItem, AssetCategory, UserAssetHolding


@admin.register(AssetCategory)
class AssetCategoryAdmin(admin.ModelAdmin):
    list_display = ("code", "title_fa", "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")
    search_fields = ("code", "title_fa")


@admin.register(AssetCatalogItem)
class AssetCatalogItemAdmin(admin.ModelAdmin):
    list_display = ("code", "name_fa", "category", "risk_level", "unit", "is_active")
    list_filter = ("category", "risk_level", "unit", "is_active")
    search_fields = ("code", "name_fa")


@admin.register(UserAssetHolding)
class UserAssetHoldingAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "asset", "quantity", "unit", "updated_at")
    search_fields = ("user__username", "asset__code", "asset__name_fa")
    readonly_fields = ("user", "asset", "quantity", "unit", "note", "created_at", "updated_at")

