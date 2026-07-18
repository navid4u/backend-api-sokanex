from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User

from .models import LiveEvent


class LiveEventAPITests(APITestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            username="live_customer",
            email="live_customer@example.com",
            password="StrongPass123!",
            role=User.Role.USER,
        )
        self.trader = User.objects.create_user(
            username="live_trader",
            email="live_trader@example.com",
            password="StrongPass123!",
            role=User.Role.TRADER,
        )
        self.employee = User.objects.create_user(
            username="live_employee",
            email="live_employee@example.com",
            password="StrongPass123!",
            role=User.Role.EMPLOYEE,
        )

        now = timezone.now()

        self.live_event = LiveEvent.objects.create(
            title="Market Analysis Live",
            description="Live market analysis",
            stream_url="https://stream.example.com/live",
            starts_at=now - timedelta(minutes=30),
            ends_at=now + timedelta(minutes=30),
            status=LiveEvent.Status.LIVE,
            host=self.trader,
            created_by=self.employee,
            is_active=True,
        )
        self.upcoming_event = LiveEvent.objects.create(
            title="Upcoming Trading Class",
            starts_at=now + timedelta(days=1),
            status=LiveEvent.Status.SCHEDULED,
            created_by=self.employee,
            is_active=True,
        )
        self.cancelled_event = LiveEvent.objects.create(
            title="Cancelled Event",
            starts_at=now + timedelta(days=2),
            status=LiveEvent.Status.CANCELLED,
            created_by=self.employee,
            is_active=True,
        )
        self.inactive_event = LiveEvent.objects.create(
            title="Inactive Event",
            starts_at=now + timedelta(days=3),
            status=LiveEvent.Status.SCHEDULED,
            created_by=self.employee,
            is_active=False,
        )

        self.list_url = reverse("live-list-create")
        self.management_url = reverse(
            "live-management-list"
        )

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def test_event_list_requires_authentication(self):
        response = self.client.get(self.list_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_customer_list_contains_only_public_events(self):
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
            self.live_event.title,
            titles,
        )
        self.assertIn(
            self.upcoming_event.title,
            titles,
        )
        self.assertNotIn(
            self.cancelled_event.title,
            titles,
        )
        self.assertNotIn(
            self.inactive_event.title,
            titles,
        )

    def test_live_event_reports_is_live_now(self):
        self.authenticate(self.customer)

        url = reverse(
            "live-detail",
            kwargs={
                "slug": self.live_event.slug,
            },
        )

        response = self.client.get(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertTrue(
            response.data["is_live_now"]
        )
        self.assertEqual(
            response.data["host"],
            self.trader.username,
        )

    def test_customer_cannot_retrieve_cancelled_event(self):
        self.authenticate(self.customer)

        url = reverse(
            "live-detail",
            kwargs={
                "slug": self.cancelled_event.slug,
            },
        )

        response = self.client.get(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_employee_management_list_contains_all_events(self):
        self.authenticate(self.employee)

        response = self.client.get(
            self.management_url
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        titles = [
            item["title"]
            for item in response.data["results"]
        ]

        self.assertIn(
            self.cancelled_event.title,
            titles,
        )
        self.assertIn(
            self.inactive_event.title,
            titles,
        )

    def test_customer_cannot_access_management_list(self):
        self.authenticate(self.customer)

        response = self.client.get(
            self.management_url
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_employee_can_create_event_and_is_saved_as_creator(
        self
    ):
        self.authenticate(self.employee)

        starts_at = (
            timezone.now()
            + timedelta(days=4)
        )

        payload = {
            "title": "New Live Class",
            "description": "A new class",
            "starts_at": starts_at.isoformat(),
            "status": LiveEvent.Status.SCHEDULED,
            "host": self.trader.pk,
            "is_active": True,
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

        event = LiveEvent.objects.get(
            title="New Live Class"
        )

        self.assertEqual(
            event.created_by,
            self.employee,
        )
        self.assertEqual(
            event.host,
            self.trader,
        )
        self.assertTrue(event.slug)

    def test_customer_and_trader_cannot_create_event(self):
        payload = {
            "title": "Forbidden Event",
            "starts_at": (
                timezone.now()
                + timedelta(days=5)
            ).isoformat(),
            "status": LiveEvent.Status.SCHEDULED,
        }

        for user in (
            self.customer,
            self.trader,
        ):
            self.authenticate(user)

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
            LiveEvent.objects.filter(
                title="Forbidden Event",
            ).exists()
        )

    def test_live_status_requires_stream_url(self):
        self.authenticate(self.employee)

        payload = {
            "title": "Live Without URL",
            "starts_at": timezone.now().isoformat(),
            "status": LiveEvent.Status.LIVE,
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
            "stream_url",
            response.data["errors"],
        )

    def test_end_time_must_be_after_start_time(self):
        self.authenticate(self.employee)

        starts_at = (
            timezone.now()
            + timedelta(days=6)
        )

        payload = {
            "title": "Invalid Time Event",
            "starts_at": starts_at.isoformat(),
            "ends_at": (
                starts_at
                - timedelta(hours=1)
            ).isoformat(),
            "status": LiveEvent.Status.SCHEDULED,
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
            "ends_at",
            response.data["errors"],
        )

    def test_employee_can_update_event(self):
        self.authenticate(self.employee)

        url = reverse(
            "live-detail",
            kwargs={
                "slug": self.upcoming_event.slug,
            },
        )

        response = self.client.patch(
            url,
            {
                "status": LiveEvent.Status.LIVE,
                "stream_url": (
                    "https://stream.example.com/"
                    "new-live"
                ),
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.upcoming_event.refresh_from_db()

        self.assertEqual(
            self.upcoming_event.status,
            LiveEvent.Status.LIVE,
        )
        self.assertEqual(
            self.upcoming_event.stream_url,
            (
                "https://stream.example.com/"
                "new-live"
            ),
        )

    def test_only_employee_can_delete_event(self):
        customer_url = reverse(
            "live-detail",
            kwargs={
                "slug": self.upcoming_event.slug,
            },
        )

        self.authenticate(self.customer)

        customer_response = self.client.delete(
            customer_url
        )

        self.assertEqual(
            customer_response.status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertTrue(
            LiveEvent.objects.filter(
                pk=self.upcoming_event.pk,
            ).exists()
        )

        employee_url = reverse(
            "live-detail",
            kwargs={
                "slug": self.cancelled_event.slug,
            },
        )

        self.authenticate(self.employee)

        employee_response = self.client.delete(
            employee_url
        )

        self.assertEqual(
            employee_response.status_code,
            status.HTTP_204_NO_CONTENT,
        )
        self.assertFalse(
            LiveEvent.objects.filter(
                pk=self.cancelled_event.pk,
            ).exists()
        )