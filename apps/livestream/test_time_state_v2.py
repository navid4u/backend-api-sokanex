import base64
import tempfile
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import User
from .models import LiveEvent


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class LiveManualStatusTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="live-v2", password="pass", access_level=1
        )
        self.employee = User.objects.create_user(
            username="live-admin-v2", password="pass", role=User.Role.EMPLOYEE
        )
        self.now = timezone.now()

    def authenticate(self, user):
        self.client.force_authenticate(user)

    def create_event(self, status, **kwargs):
        defaults = {
            "title": f"{status} event",
            "starts_at": self.now + timedelta(hours=2),
            "ends_at": self.now + timedelta(hours=3),
            "external_url": f"https://live.example/{status.lower()}",
            "status": status,
            "created_by": self.employee,
            "is_active": True,
        }
        defaults.update(kwargs)
        return LiveEvent.objects.create(**defaults)

    def test_multipart_active_create_with_thumbnail_url_and_aware_times(self):
        self.authenticate(self.employee)
        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        response = self.client.post(
            "/api/livestream/",
            {
                "title": "Active multipart",
                "description": "Manual live",
                "thumbnail": SimpleUploadedFile("live.png", png, content_type="image/png"),
                "host": self.employee.pk,
                "starts_at": self.now.isoformat(),
                "ends_at": (self.now + timedelta(hours=1)).isoformat(),
                "external_url": "https://live.example/active",
                "status": "ACTIVE",
                "allowed_levels": [1, 2, 3, 4, 5],
            },
            format="multipart",
            secure=True,
        )
        self.assertEqual(response.status_code, 201, response.data)
        event = LiveEvent.objects.get(pk=response.data["id"])
        self.assertTrue(timezone.is_aware(event.starts_at))
        self.assertEqual(event.status, LiveEvent.Status.ACTIVE)
        self.assertTrue(response.data["thumbnail"].startswith("https://"))

    def test_all_four_statuses_are_accepted_by_create_and_patch(self):
        self.authenticate(self.employee)
        statuses = ["ACTIVE", "ENDED", "UPCOMING", "WITHIN_HOUR"]
        for index, status_value in enumerate(statuses):
            response = self.client.post(
                "/api/livestream/",
                {
                    "title": f"Status {index}",
                    "starts_at": (self.now + timedelta(days=index + 1)).isoformat(),
                    "external_url": "https://live.example/join",
                    "status": status_value,
                },
                format="json",
            )
            self.assertEqual(response.status_code, 201, response.data)
            patched_status = statuses[(index + 1) % len(statuses)]
            patched = self.client.patch(
                f"/api/livestream/{response.data['slug']}/",
                {"status": patched_status},
                format="json",
            )
            self.assertEqual(patched.status_code, 200, patched.data)
            self.assertEqual(patched.data["status"], patched_status)

    def test_changing_times_never_changes_manual_status(self):
        event = self.create_event(LiveEvent.Status.WITHIN_HOUR)
        self.authenticate(self.employee)
        response = self.client.patch(
            f"/api/livestream/{event.slug}/",
            {
                "starts_at": (self.now - timedelta(days=10)).isoformat(),
                "ends_at": (self.now - timedelta(days=9)).isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        event.refresh_from_db()
        self.assertEqual(event.status, LiveEvent.Status.WITHIN_HOUR)

    def test_public_list_returns_every_manual_status_and_newest_first(self):
        events = [self.create_event(value) for value in LiveEvent.Status.values]
        self.authenticate(self.user)
        response = self.client.get("/api/livestream/")
        self.assertEqual(response.status_code, 200)
        returned = response.data["results"]
        self.assertEqual({row["status"] for row in returned}, set(LiveEvent.Status.values))
        self.assertEqual(
            [row["id"] for row in returned],
            [event.id for event in sorted(events, key=lambda item: (item.starts_at, item.id), reverse=True)],
        )

    def test_public_links_are_only_exposed_for_active_status(self):
        events = {value: self.create_event(value) for value in LiveEvent.Status.values}
        self.authenticate(self.user)
        for status_value, event in events.items():
            response = self.client.get(f"/api/livestream/{event.slug}/")
            self.assertEqual(response.status_code, 200)
            if status_value == LiveEvent.Status.ACTIVE:
                self.assertEqual(response.data["external_url"], event.external_url)
                self.assertEqual(response.data["join_url"], event.external_url)
                self.assertTrue(response.data["can_join"])
            else:
                self.assertEqual(response.data["external_url"], "")
                self.assertEqual(response.data["join_url"], "")
                self.assertFalse(response.data["can_join"])

    def test_management_keeps_stored_link_for_non_active_event(self):
        event = self.create_event(LiveEvent.Status.UPCOMING)
        self.authenticate(self.employee)
        listing = self.client.get("/api/livestream/manage/")
        self.assertEqual(listing.status_code, 200)
        row = next(item for item in listing.data["results"] if item["id"] == event.id)
        self.assertEqual(row["external_url"], event.external_url)
        detail = self.client.get(f"/api/livestream/{event.slug}/")
        self.assertEqual(detail.data["external_url"], event.external_url)

    def test_access_levels_still_scope_public_events(self):
        event = self.create_event(
            LiveEvent.Status.ACTIVE,
            allowed_level_1=False,
            allowed_level_2=True,
        )
        self.authenticate(self.user)
        self.assertEqual(self.client.get(f"/api/livestream/{event.slug}/").status_code, 404)
        self.user.access_level = 2
        self.user.save(update_fields=("access_level", "updated_at"))
        self.assertEqual(self.client.get(f"/api/livestream/{event.slug}/").status_code, 200)
