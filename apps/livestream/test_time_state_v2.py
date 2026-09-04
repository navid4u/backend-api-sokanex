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

    def test_join_window_disabled_access_and_replay(self):
        now = timezone.now()
        event = LiveEvent.objects.create(
            title="Early window", starts_at=now + timedelta(minutes=9),
            ends_at=now + timedelta(hours=1), join_early_minutes=10,
            external_url="https://live.example/early", created_by=self.admin,
        )
        response = self.client.get(f"/api/livestream/{event.slug}/")
        self.assertTrue(response.data["can_join"])
        self.assertEqual(response.data["join_url"], "https://live.example/early")
        event.status = LiveEvent.Status.DISABLED
        event.save(update_fields=("status", "updated_at"))
        self.assertEqual(self.client.get(f"/api/livestream/{event.slug}/").status_code, 404)

        ended = LiveEvent.objects.create(
            title="Ended", starts_at=now - timedelta(hours=2), ends_at=now - timedelta(hours=1),
            replay_url="https://live.example/replay", created_by=self.admin,
        )
        ended_response = self.client.get(f"/api/livestream/{ended.slug}/")
        self.assertFalse(ended_response.data["can_join"])
        self.assertEqual(ended_response.data["join_url"], "")
        self.assertEqual(ended_response.data["replay_url"], "https://live.example/replay")

    def test_level_access_and_before_window_hides_url(self):
        event = LiveEvent.objects.create(
            title="Level two", starts_at=timezone.now() + timedelta(hours=1),
            ends_at=timezone.now() + timedelta(hours=2), external_url="https://secret.example/live",
            allowed_level_1=False, allowed_level_2=True, created_by=self.admin,
        )
        self.assertEqual(self.client.get(f"/api/livestream/{event.slug}/").status_code, 404)
        self.user.access_level = 2
        self.user.save(update_fields=("access_level", "updated_at"))
        response = self.client.get(f"/api/livestream/{event.slug}/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["can_join"])
        self.assertEqual(response.data["join_url"], "")
        self.assertEqual(response.data["external_url"], "")
