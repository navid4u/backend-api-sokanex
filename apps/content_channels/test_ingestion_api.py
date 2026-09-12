from django.test import override_settings
from unittest.mock import patch
from rest_framework.test import APITestCase

from apps.accounts.models import User

from .models import Channel, ChannelPost


@override_settings(CONTENT_INGESTION_API_KEY="test-secret-key")
class InternalAnalysisIngestionTests(APITestCase):
    def setUp(self):
        User.objects.get_or_create(
            username="sokanex-feed-bot",
            defaults={"password": "!", "is_active": False},
        )
        Channel.objects.get_or_create(
            slug="internal-analysis",
            defaults={"name": "Internal Analysis"},
        )
        self.url = "/api/channels/internal-analysis/ingest/"
        self.headers = {"HTTP_X_SOKANEX_INGEST_KEY": "test-secret-key"}

    def test_publishes_immediately_and_supports_forex(self):
        response = self.client.post(
            self.url,
            {"external_id": "telegram-analysis-1", "scope": "FOREX", "title": "عنوان", "body": "متن تحلیل"},
            format="multipart",
            **self.headers,
        )
        self.assertEqual(response.status_code, 201)
        post = ChannelPost.objects.get(external_id="telegram-analysis-1")
        self.assertEqual(post.status, ChannelPost.Status.PUBLISHED)
        self.assertEqual(post.source, ChannelPost.Source.TELEGRAM_API)
        self.assertIsNotNone(post.published_at)

    def test_external_id_is_idempotent(self):
        payload = {"external_id": "telegram-analysis-retry", "scope": "GOLD", "title": "طلا", "body": "تحلیل"}
        self.assertEqual(self.client.post(self.url, payload, format="json", **self.headers).status_code, 201)
        self.assertEqual(self.client.post(self.url, payload, format="json", **self.headers).status_code, 200)
        self.assertEqual(ChannelPost.objects.filter(external_id="telegram-analysis-retry").count(), 1)

    @patch("apps.content_channels.views.get_channel_layer")
    def test_realtime_failure_does_not_fail_persisted_ingestion(self, get_channel_layer):
        get_channel_layer.side_effect = ConnectionError("redis unavailable")

        response = self.client.post(
            self.url,
            {"external_id": "telegram-analysis-realtime-failure", "scope": "GOLD", "title": "طلا", "body": "تحلیل"},
            format="json",
            **self.headers,
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(ChannelPost.objects.filter(external_id="telegram-analysis-realtime-failure").exists())

    def test_invalid_key_is_rejected(self):
        response = self.client.post(self.url, {"scope": "GOLD", "title": "x", "body": "y"}, format="json", HTTP_X_SOKANEX_INGEST_KEY="wrong")
        self.assertEqual(response.status_code, 401)

    def test_feed_filter_hides_legacy_rows(self):
        bot = User.objects.get(username="sokanex-feed-bot")
        channel = Channel.objects.get(slug="internal-analysis")
        ChannelPost.objects.create(channel=channel, author=bot, title="قدیمی", body="قدیمی", scope="GOLD", status="PUBLISHED", published_at="2026-01-01T00:00:00Z")
        self.client.force_authenticate(User.objects.create_user(username="viewer", password="pass"))
        response = self.client.get("/api/channels/internal-analysis/?source=TELEGRAM_API")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 0)
