from django.urls import path

from .views import (
    MarkAllNotificationsReadView,
    MarkNotificationReadView,
    NotificationDetailView,
    NotificationListCreateView,
    NotificationUnreadCountView,
)


urlpatterns = [
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