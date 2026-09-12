from django.test import override_settings
from rest_framework.test import APITestCase

from apps.accounts.models import User

from .models import Signal


@override_settings(CONTENT_INGESTION_API_KEY="test-secret-key")
class SignalIngestionTests(APITestCase):
    def setUp(self):
        User.objects.get_or_create(username="sokanex-feed-bot", defaults={"password": "!", "is_active": False})
        self.url = "/api/signals/ingest/"
        self.headers = {"HTTP_X_SOKANEX_INGEST_KEY": "test-secret-key"}

    def test_minimal_signal_is_approved_and_visible_to_every_level(self):
        response = self.client.post(
            self.url,
            {"external_id": "telegram-signal-1", "title": "سیگنال جدید", "description": "توضیحات سیگنال"},
            format="multipart",
            **self.headers,
        )
        self.assertEqual(response.status_code, 201)
        signal = Signal.objects.get(external_id="telegram-signal-1")
        self.assertEqual(signal.status, "approved")
        self.assertEqual(signal.source, Signal.Source.TELEGRAM_API)
        self.assertEqual(signal.allowed_levels, [1, 2, 3, 4, 5])

    def test_external_id_prevents_retry_duplicate(self):
        payload = {"external_id": "telegram-signal-retry", "title": "عنوان", "description": "متن"}
        self.assertEqual(self.client.post(self.url, payload, format="json", **self.headers).status_code, 201)
        self.assertEqual(self.client.post(self.url, payload, format="json", **self.headers).status_code, 200)
        self.assertEqual(Signal.objects.filter(external_id="telegram-signal-retry").count(), 1)

    def test_feed_filter_excludes_legacy_signals(self):
        viewer = User.objects.create_user(username="signal-viewer", password="pass")
        self.client.force_authenticate(viewer)
        response = self.client.get("/api/signals/?source=TELEGRAM_API")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 0)
