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
from .sms_automation_api import (
    SMSAutomationStatusView, SMSRuleListView, SMSRuleDetailView,
    SMSDeliveryListView, SMSBroadcastPreviewView, SMSBroadcastCreateView,
    SMSBroadcastListView,
)


urlpatterns = [
    path("sms-automation/status/", SMSAutomationStatusView.as_view(), name="sms-automation-status"),
    path("sms-automation/rules/", SMSRuleListView.as_view(), name="sms-automation-rules"),
    path("sms-automation/rules/<int:pk>/", SMSRuleDetailView.as_view(), name="sms-automation-rule-detail"),
    path("sms-automation/deliveries/", SMSDeliveryListView.as_view(), name="sms-automation-deliveries"),
    path("sms-automation/broadcasts/preview/", SMSBroadcastPreviewView.as_view(), name="sms-broadcast-preview"),
    path("sms-automation/broadcasts/send/", SMSBroadcastCreateView.as_view(), name="sms-broadcast-send"),
    path("sms-automation/broadcasts/", SMSBroadcastListView.as_view(), name="sms-broadcasts"),
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
