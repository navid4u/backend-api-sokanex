from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from django.views.decorators.cache import never_cache

from apps.accounts.views import (
    CustomTokenObtainPairView,
)
from apps.accounts.jwt import DeviceAwareTokenRefreshView

from .views import (
    health_check,
    home,
)

urlpatterns = [
    path("", home),

    path(
        "api/health/",
        health_check,
        name="health-check",
    ),

    path(
        "admin/",
        admin.site.urls,
    ),
    path(
        "api/schema/",
        SpectacularAPIView.as_view(),
        name="api-schema",
    ),

    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(
            url_name="api-schema"
        ),
        name="api-docs",
    ),

    path(
        "api/redoc/",
        SpectacularRedocView.as_view(
            url_name="api-schema"
        ),
        name="api-redoc",
    ),
    path(
        "api/accounts/",
        include("apps.accounts.urls"),
    ),
    path(
        "api/activity/",
        include("apps.activity.urls"),
    ),

    path(
        "api/token/",
        CustomTokenObtainPairView.as_view(),
        name="token-obtain-pair",
    ),

    path(
        "api/token/refresh/",
        never_cache(DeviceAwareTokenRefreshView.as_view()),
        name="token-refresh",
    ),

    path(
        "api/dashboard/",
        include("apps.dashboard.urls"),
    ),

    path(
        "api/signals/",
        include("apps.signals.urls"),
    ),
    path(
        "api/articles/",
        include("apps.articles.urls"),
    ),
    
    path(
        "api/wallet/",
        include("apps.wallet.urls"),
    ),
    path(
        "api/videos/",
        include("apps.videos.urls"),
    ),
    
    path(
        "api/notifications/",
        include("apps.notifications.urls"),
    ),
    path(
        "api/brokers/",
        include("apps.brokers.urls"),
    ),
    path(
        "api/livestream/",
        include("apps.livestream.urls"),
    ),
    path(
        "api/chat/",
        include("apps.chat.urls"),
    ),
    path(
        "api/academy/",
        include("apps.academy.urls"),
    ),
    path(
        "api/landing/",
        include("landing.urls"),
    ),
    path("api/market/", include("apps.market.urls")),
    path("api/channels/", include("apps.content_channels.urls")),
    path("api/support/", include("apps.chat.support_urls")),
    path("api/", include("apps.platform_settings.urls")),
    path("api/", include("apps.wallet.billing_urls")),
]


if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )
