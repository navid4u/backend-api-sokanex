from django.urls import path

from .views import (
    LandingPageManagementView,
    LandingSectionDetailView,
    LandingSectionListCreateView,
    PublicLandingView,
)


urlpatterns = [
    path(
        "",
        PublicLandingView.as_view(),
        name="landing-public",
    ),
    path(
        "manage/page/",
        LandingPageManagementView.as_view(),
        name="landing-page-management",
    ),
    path(
        "manage/sections/",
        LandingSectionListCreateView.as_view(),
        name="landing-section-list-create",
    ),
    path(
        "manage/sections/<int:pk>/",
        LandingSectionDetailView.as_view(),
        name="landing-section-detail",
    ),
]
