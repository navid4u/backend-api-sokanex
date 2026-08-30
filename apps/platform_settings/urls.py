from django.urls import path

from .views import (
    FinancialSettingsView, PublicSettingsView,
    SystemContentListView, SystemContentUpdateView,
    AdminTranslationCatalogView, PublicTranslationCatalogView,
)

urlpatterns = [
    path("platform/settings/public/", PublicSettingsView.as_view(), name="platform-public-settings"),
    path("admin/platform/financial-settings/", FinancialSettingsView.as_view(), name="platform-financial-settings"),
    path("admin/platform/content/", SystemContentListView.as_view(), name="platform-content-list"),
    path("admin/platform/content/<str:key>/", SystemContentUpdateView.as_view(), name="platform-content-update"),
    path("admin/platform/translations/", AdminTranslationCatalogView.as_view(), name="platform-admin-translations"),
    path("platform/translations/<str:locale>/", PublicTranslationCatalogView.as_view(), name="platform-public-translations"),
]
