from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from common.sms import SMSProviderError
from .models import Notification, NotificationSMSDelivery
from .services import NotificationService


@override_settings(
    PAYAMITO_ENABLED=True,
    PAYAMITO_USERNAME="api-user",
    PAYAMITO_API_KEY="api-key",
    PAYAMITO_FROM_NUMBER="9981803296",
    PAYAMITO_OTP_MESSAGE_TEMPLATE="Login code: {code}",
    PAYAMITO_NOTIFICATION_MESSAGE_TEMPLATE="New notification: {title}",
    PAYAMITO_SMS_RETRY_LIMIT=3,
    PAYAMITO_SMS_SEND_INLINE=True,
)
class NotificationSMSTests(APITestCase):
    def setUp(self):
        self.employee = User.objects.create_user(
            username="sms-employee", password="StrongPass123!", role=User.Role.EMPLOYEE
        )
        self.level_1 = User.objects.create_user(
            username="09120000001", phone="09120000001", password="StrongPass123!", access_level=1
        )
        self.level_2 = User.objects.create_user(
            username="09120000002", phone="09120000002", password="StrongPass123!", access_level=2
        )
        User.objects.create_user(
            username="no-phone", password="StrongPass123!", access_level=2
        )
        self.client.force_authenticate(self.employee)

    @patch("apps.notifications.services.PayamitoSMSService.send")
    def test_create_notification_targets_selected_levels_and_sends_title(self, send):
        send.return_value = {"message_id": "1234567890123456", "status": "Ok"}
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("notification-list-create"), {
                "title": "Gold alert", "message": "Open the app for details",
                "allowed_levels": [2], "send_sms": True, "target_url": "/articles/12",
            }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        notification = Notification.objects.get(title="Gold alert")
        self.assertEqual(notification.target_url, "/articles/12")
        self.assertEqual(notification.allowed_levels, [2])
        delivery = NotificationSMSDelivery.objects.get()
        self.assertEqual(delivery.user_id, self.level_2.id)
        self.assertEqual(delivery.status, NotificationSMSDelivery.Status.SENT)
        send.assert_called_once_with("09120000002", "New notification: Gold alert")

    @patch("apps.notifications.services.PayamitoSMSService.send")
    def test_sms_failure_does_not_rollback_notification_and_can_retry(self, send):
        send.side_effect = SMSProviderError("temporary", provider_code="6")
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("notification-list-create"), {
                "title": "Retry alert", "message": "Details", "recipient": self.level_1.id,
                "send_sms": True,
            }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        delivery = NotificationSMSDelivery.objects.get()
        self.assertEqual(delivery.status, NotificationSMSDelivery.Status.FAILED)
        self.assertEqual(delivery.provider_code, "6")
        send.side_effect = None
        send.return_value = {"message_id": "9999999999999999", "status": "Ok"}
        NotificationService.send_pending_sms()
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, NotificationSMSDelivery.Status.SENT)
        self.assertEqual(delivery.attempts, 2)

    @patch("apps.notifications.services.PayamitoSMSService.send")
    def test_send_sms_false_creates_no_delivery(self, send):
        response = self.client.post(reverse("notification-list-create"), {
            "title": "In app only", "message": "Details", "allowed_levels": [1],
            "send_sms": False,
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(NotificationSMSDelivery.objects.exists())
        send.assert_not_called()

    def test_level_restricted_notification_visibility(self):
        Notification.objects.create(
            title="Level 2", message="Only level 2", created_by=self.employee,
            allowed_level_1=False, allowed_level_2=True, allowed_level_3=False,
            allowed_level_4=False, allowed_level_5=False,
        )
        self.client.force_authenticate(self.level_1)
        self.assertEqual(self.client.get(reverse("notification-list-create")).data["count"], 0)
        self.client.force_authenticate(self.level_2)
        self.assertEqual(self.client.get(reverse("notification-list-create")).data["count"], 1)
