from django.urls import path

from .views import (
    MarkAllNotificationsReadView,
    MarkNotificationReadView,
    NotificationDetailView,
    NotificationListCreateView,
    NotificationUnreadCountView,
    WebPushVapidPublicKeyView,
    WebPushSubscriptionListCreateView,
    WebPushSubscriptionDeleteView,
)


urlpatterns = [
    path("push/vapid-public-key/", WebPushVapidPublicKeyView.as_view(), name="push-vapid-public-key"),
    path("push/subscriptions/", WebPushSubscriptionListCreateView.as_view(), name="push-subscriptions"),
    path("push/subscriptions/<int:pk>/", WebPushSubscriptionDeleteView.as_view(), name="push-subscription-delete"),
    path(
        "",
        NotificationListCreateView.as_view(),
        name="notification-list-create",
    ),

    path(
        "unread-count/",
        NotificationUnreadCountView.as_view(),
        name="notification-unread-count",
    ),

    path(
        "read-all/",
        MarkAllNotificationsReadView.as_view(),
        name="notification-read-all",
    ),

    path(
        "<int:pk>/",
        NotificationDetailView.as_view(),
        name="notification-detail",
    ),

    path(
        "<int:pk>/read/",
        MarkNotificationReadView.as_view(),
        name="notification-read",
    ),
]
