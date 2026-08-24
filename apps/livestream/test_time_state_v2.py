from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import User
from .models import LiveEvent


class LiveTimeStateV2Tests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="live-v2", password="pass", access_level=1)
        self.admin = User.objects.create_user(username="live-admin-v2", password="pass", role=User.Role.ADMIN)
        self.client.force_authenticate(self.user)

    def test_external_url_is_hidden_before_start_and_exposed_during_live(self):
        upcoming = LiveEvent.objects.create(
            title="Upcoming", starts_at=timezone.now() + timedelta(hours=1),
            ends_at=timezone.now() + timedelta(hours=2), external_url="https://live.example/upcoming",
            created_by=self.admin,
        )
        response = self.client.get(f"/api/livestream/{upcoming.slug}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "SCHEDULED")
        self.assertEqual(response.data["external_url"], "")
        live = LiveEvent.objects.create(
            title="Now", starts_at=timezone.now() - timedelta(minutes=5),
            ends_at=timezone.now() + timedelta(minutes=55), external_url="https://live.example/now",
            created_by=self.admin,
        )
        response = self.client.get(f"/api/livestream/{live.slug}/")
        self.assertEqual(response.data["status"], "LIVE")
        self.assertEqual(response.data["external_url"], "https://live.example/now")
