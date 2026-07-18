from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User

from .models import Notification, NotificationRead


class NotificationAPITests(APITestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            username="notification_customer",
            email="notification_customer@example.com",
            password="StrongPass123!",
            role=User.Role.USER,
        )
        self.other_customer = User.objects.create_user(
            username="notification_other",
            email="notification_other@example.com",
            password="StrongPass123!",
            role=User.Role.USER,
        )
        self.trader = User.objects.create_user(
            username="notification_trader",
            email="notification_trader@example.com",
            password="StrongPass123!",
            role=User.Role.TRADER,
        )
        self.employee = User.objects.create_user(
            username="notification_employee",
            email="notification_employee@example.com",
            password="StrongPass123!",
            role=User.Role.EMPLOYEE,
        )

        self.global_notification = Notification.objects.create(
            title="Global notification",
            message="Visible to everyone",
            notification_type=Notification.Type.INFO,
            created_by=self.employee,
            is_active=True,
        )
        self.personal_notification = Notification.objects.create(
            title="Personal notification",
            message="Visible only to customer",
            notification_type=Notification.Type.SYSTEM,
            recipient=self.customer,
            created_by=self.employee,
            is_active=True,
        )
        self.trader_notification = Notification.objects.create(
            title="Trader notification",
            message="Visible only to traders",
            notification_type=Notification.Type.SIGNAL,
            target_role=User.Role.TRADER,
            created_by=self.employee,
            is_active=True,
        )
        self.inactive_notification = Notification.objects.create(
            title="Inactive notification",
            message="Must not be visible",
            notification_type=Notification.Type.INFO,
            created_by=self.employee,
            is_active=False,
        )

        self.list_url = reverse(
            "notification-list-create"
        )
        self.read_all_url = reverse(
            "notification-read-all"
        )

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def test_notification_list_requires_authentication(self):
        response = self.client.get(self.list_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_customer_sees_global_and_personal_notifications(self):
        self.authenticate(self.customer)

        response = self.client.get(self.list_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        titles = [
            item["title"]
            for item in response.data["results"]
        ]

        self.assertIn(
            self.global_notification.title,
            titles,
        )
        self.assertIn(
            self.personal_notification.title,
            titles,
        )
        self.assertNotIn(
            self.trader_notification.title,
            titles,
        )
        self.assertNotIn(
            self.inactive_notification.title,
            titles,
        )

    def test_trader_sees_role_notification(self):
        self.authenticate(self.trader)

        response = self.client.get(self.list_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        titles = [
            item["title"]
            for item in response.data["results"]
        ]

        self.assertIn(
            self.global_notification.title,
            titles,
        )
        self.assertIn(
            self.trader_notification.title,
            titles,
        )
        self.assertNotIn(
            self.personal_notification.title,
            titles,
        )

    def test_customer_cannot_retrieve_another_users_notification(
        self
    ):
        self.authenticate(self.other_customer)

        url = reverse(
            "notification-detail",
            kwargs={
                "pk": self.personal_notification.pk,
            },
        )

        response = self.client.get(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_employee_can_create_notification(self):
        self.authenticate(self.employee)

        payload = {
            "title": "New system message",
            "message": "System maintenance",
            "notification_type": Notification.Type.SYSTEM,
            "target_role": User.Role.USER,
            "target_url": "/dashboard",
        }

        response = self.client.post(
            self.list_url,
            payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        notification = Notification.objects.get(
            title="New system message"
        )

        self.assertEqual(
            notification.created_by,
            self.employee,
        )
        self.assertEqual(
            notification.target_role,
            User.Role.USER,
        )

    def test_customer_cannot_create_notification(self):
        self.authenticate(self.customer)

        payload = {
            "title": "Forbidden notification",
            "message": "Must not be created",
            "notification_type": Notification.Type.INFO,
        }

        response = self.client.post(
            self.list_url,
            payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertFalse(
            Notification.objects.filter(
                title="Forbidden notification"
            ).exists()
        )

    def test_recipient_and_target_role_cannot_be_used_together(
        self
    ):
        self.authenticate(self.employee)

        payload = {
            "title": "Invalid notification",
            "message": "Invalid targeting",
            "notification_type": Notification.Type.INFO,
            "recipient": self.customer.pk,
            "target_role": User.Role.USER,
        }

        response = self.client.post(
            self.list_url,
            payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn(
            "non_field_errors",
            response.data["errors"],
        )

    def test_invalid_target_role_is_rejected(self):
        self.authenticate(self.employee)

        payload = {
            "title": "Invalid role",
            "message": "Invalid target role",
            "target_role": "UNKNOWN_ROLE",
        }

        response = self.client.post(
            self.list_url,
            payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn(
            "target_role",
            response.data["errors"],
        )

    def test_customer_can_mark_notification_as_read(self):
        self.authenticate(self.customer)

        url = reverse(
            "notification-read",
            kwargs={
                "pk": self.personal_notification.pk,
            },
        )

        response = self.client.post(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertTrue(
            NotificationRead.objects.filter(
                notification=self.personal_notification,
                user=self.customer,
            ).exists()
        )

        detail_url = reverse(
            "notification-detail",
            kwargs={
                "pk": self.personal_notification.pk,
            },
        )

        detail_response = self.client.get(detail_url)

        self.assertTrue(
            detail_response.data["is_read"]
        )

    def test_mark_notification_as_read_is_idempotent(self):
        self.authenticate(self.customer)

        url = reverse(
            "notification-read",
            kwargs={
                "pk": self.personal_notification.pk,
            },
        )

        self.client.post(url)
        second_response = self.client.post(url)

        self.assertEqual(
            second_response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            NotificationRead.objects.filter(
                notification=self.personal_notification,
                user=self.customer,
            ).count(),
            1,
        )

    def test_customer_can_mark_all_visible_notifications_as_read(
        self
    ):
        self.authenticate(self.customer)

        response = self.client.post(
            self.read_all_url
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            response.data["marked_count"],
            2,
        )
        self.assertEqual(
            NotificationRead.objects.filter(
                user=self.customer,
            ).count(),
            2,
        )

    def test_filter_notifications_by_read_status(self):
        NotificationRead.objects.create(
            notification=self.personal_notification,
            user=self.customer,
        )

        self.authenticate(self.customer)

        read_response = self.client.get(
            self.list_url,
            {
                "is_read": "true",
            },
        )
        unread_response = self.client.get(
            self.list_url,
            {
                "is_read": "false",
            },
        )

        self.assertEqual(
            read_response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            unread_response.status_code,
            status.HTTP_200_OK,
        )

        read_titles = [
            item["title"]
            for item in read_response.data["results"]
        ]
        unread_titles = [
            item["title"]
            for item in unread_response.data["results"]
        ]

        self.assertIn(
            self.personal_notification.title,
            read_titles,
        )
        self.assertNotIn(
            self.personal_notification.title,
            unread_titles,
        )
        self.assertIn(
            self.global_notification.title,
            unread_titles,
        )