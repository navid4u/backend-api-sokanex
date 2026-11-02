from django.urls import path

from .views import (
    PlatformCompareView, PlatformFieldListView, PlatformManageDetailView,
    PlatformManageFieldDetailView, PlatformManageFieldsView, PlatformManageListView,
    PlatformPublicDetailView, PlatformPublicListView,
)


urlpatterns = [
    path("fields/", PlatformFieldListView.as_view(), name="market-platform-fields"),
    path("compare/", PlatformCompareView.as_view(), name="market-platform-compare"),
    path("manage/fields/<int:pk>/", PlatformManageFieldDetailView.as_view(), name="market-platform-manage-field-detail"),
    path("manage/fields/", PlatformManageFieldsView.as_view(), name="market-platform-manage-fields"),
    path("manage/<int:pk>/", PlatformManageDetailView.as_view(), name="market-platform-manage-detail"),
    path("manage/", PlatformManageListView.as_view(), name="market-platform-manage-list"),
    path("<int:pk>/", PlatformPublicDetailView.as_view(), name="market-platform-detail"),
    path("", PlatformPublicListView.as_view(), name="market-platform-list"),
]
