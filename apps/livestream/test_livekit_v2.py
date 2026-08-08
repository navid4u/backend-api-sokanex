from types import SimpleNamespace
from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import PlatformRole, User
from .models import LiveChatMessage, LiveEvent, LivePresence, LiveRecording


LIVEKIT_SETTINGS = override_settings(
    LIVEKIT_URL="wss://live.example.com",
    LIVEKIT_API_URL="https://live.example.com",
    LIVEKIT_API_KEY="test-api-key",
    LIVEKIT_API_SECRET="test-api-secret-with-at-least-32-characters",
)


@LIVEKIT_SETTINGS
class LiveKitV2Tests(APITestCase):
    def setUp(self):
        self.employee = User.objects.create_user(username="live-manager", password="StrongPass123!", role=User.Role.EMPLOYEE)
        self.viewer = User.objects.create_user(username="live-viewer", password="StrongPass123!", role=User.Role.USER)
        self.other = User.objects.create_user(username="live-other", password="StrongPass123!", role=User.Role.USER)
        role = PlatformRole.objects.create(
            name="Live producer", slug="live-producer", permissions=[User.Permission.LIVE_MANAGE], created_by=self.employee,
        )
        self.producer = User.objects.create_user(
            username="live-producer", password="StrongPass123!", role=User.Role.USER, custom_role=role,
        )
        self.event = LiveEvent.objects.create(
            title="Daily Live Trade", starts_at=timezone.now(), status=LiveEvent.Status.LIVE,
            host=self.employee, created_by=self.employee, max_participants=50,
            viewer_display_offset=100, comments_enabled=True, recording_enabled=True,
        )

    def auth(self, user):
        self.client.force_authenticate(user)

    def test_employee_and_custom_permission_can_manage_while_user_cannot(self):
        for actor in (self.employee, self.producer):
            self.auth(actor)
            response = self.client.get(reverse("live-management-list"))
            self.assertEqual(response.status_code, 200)
        self.auth(self.viewer)
        self.assertEqual(self.client.get(reverse("live-management-list")).status_code, 403)

    def test_join_returns_signed_media_contract_and_real_display_counts(self):
        self.auth(self.viewer)
        response = self.client.post(reverse("live-join", kwargs={"slug": self.event.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["livekit_url"], "wss://live.example.com")
        self.assertTrue(response.data["participant_token"])
        self.assertFalse(response.data["can_publish"])
        self.assertEqual(response.data["actual_viewer_count"], 1)
        self.assertEqual(response.data["display_viewer_count"], 101)

    def test_capacity_limit_is_enforced_server_side(self):
        self.event.max_participants = 1
        self.event.save(update_fields=("max_participants", "updated_at"))
        LivePresence.objects.create(event=self.event, user=self.other)
        self.auth(self.viewer)
        response = self.client.post(reverse("live-join", kwargs={"slug": self.event.slug}))
        self.assertEqual(response.status_code, 409)

    def test_only_host_sees_participant_rows(self):
        LivePresence.objects.create(event=self.event, user=self.viewer)
        self.auth(self.viewer)
        audience = self.client.get(reverse("live-presence", kwargs={"slug": self.event.slug}))
        self.assertEqual(audience.data["results"], [])
        self.auth(self.employee)
        host = self.client.get(reverse("live-presence", kwargs={"slug": self.event.slug}))
        self.assertEqual(len(host.data["results"]), 1)
        self.assertEqual(host.data["actual_viewer_count"], 1)

    def test_public_comment_is_sanitized_broadcast_and_moderatable(self):
        self.auth(self.viewer)
        response = self.client.post(
            reverse("live-chat", kwargs={"slug": self.event.slug}), {"text": "<b>Hello</b> traders"}, format="json",
        )
        self.assertEqual(response.status_code, 201)
        message = LiveChatMessage.objects.get(pk=response.data["id"])
        self.assertEqual(message.text, "Hello traders")
        self.auth(self.employee)
        deleted = self.client.delete(
            reverse("live-chat-delete", kwargs={"slug": self.event.slug, "message_id": message.pk})
        )
        self.assertEqual(deleted.status_code, 204)
        message.refresh_from_db()
        self.assertTrue(message.is_deleted)

    @patch("apps.livestream.views.start_recording")
    def test_host_can_start_recording_and_metadata_is_persisted(self, mocked_start):
        mocked_start.return_value = (SimpleNamespace(egress_id="EG_test"), "recordings/test.mp4")
        self.auth(self.employee)
        response = self.client.post(reverse("live-recording-list-start", kwargs={"slug": self.event.slug}))
        self.assertEqual(response.status_code, 201)
        recording = LiveRecording.objects.get(egress_id="EG_test")
        self.assertEqual(recording.status, LiveRecording.Status.STARTING)
        self.assertEqual(recording.started_by, self.employee)

    def test_host_can_start_and_end_scheduled_event(self):
        self.event.status = LiveEvent.Status.SCHEDULED
        self.event.save(update_fields=("status", "updated_at"))
        self.auth(self.employee)
        started = self.client.post(reverse("live-start", kwargs={"slug": self.event.slug}))
        self.assertEqual(started.status_code, 200)
        ended = self.client.post(reverse("live-end", kwargs={"slug": self.event.slug}))
        self.assertEqual(ended.status_code, 200)
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, LiveEvent.Status.ENDED)
        self.assertIsNotNone(self.event.ended_at)
