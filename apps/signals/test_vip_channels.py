import base64
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import User

from .models import VIPSignalPost


@override_settings(SIGNAL_CHANNEL_INGESTION_API_KEY="vip-test-key")
class VIPSignalChannelTests(APITestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media = tempfile.TemporaryDirectory()
        cls._media_override = override_settings(MEDIA_ROOT=cls._media.name)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        cls._media.cleanup()
        super().tearDownClass()

    def setUp(self):
        User.objects.get_or_create(
            username="sokanex-feed-bot",
            defaults={"is_active": False},
        )
        self.user = User.objects.create_user(username="viewer", password="pass")
        self.admin = User.objects.create_user(
            username="admin", password="pass", role=User.Role.ADMIN
        )
        self.ingestion_headers = {"HTTP_X_SOKANEX_SIGNAL_KEY": "vip-test-key"}

    def test_crypto_ingestion_and_default_feed(self):
        response = self.client.post(
            "/api/signals/channels/crypto/ingest/",
            {"external_id": "crypto-100", "text": " ".join(f"word{i}" for i in range(35))},
            format="multipart",
            **self.ingestion_headers,
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["channel"], "CRYPTO")
        self.assertTrue(response.data["excerpt"].endswith("…"))

        self.client.force_authenticate(self.user)
        feed = self.client.get("/api/signals/")
        self.assertEqual(feed.status_code, 200)
        self.assertEqual(feed.data["count"], 1)
        self.assertEqual(feed.data["results"][0]["channel"], "CRYPTO")

    def test_ingestion_sanitizes_text_and_uploads_image(self):
        image = SimpleUploadedFile(
            "telegram.png",
            base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
            ),
            content_type="image/png",
        )
        response = self.client.post(
            "/api/signals/channels/forex/ingest/",
            {"text": "<script>alert(1)</script><b>تحلیل فارکس</b>", "image": image},
            format="multipart",
            **self.ingestion_headers,
        )
        self.assertEqual(response.status_code, 201)
        self.assertNotIn("<", response.data["text"])
        post = VIPSignalPost.objects.get()
        self.assertTrue(post.image.name.startswith("signals/vip/forex/"))
        self.assertTrue(response.data["image"].startswith("http"))

    def test_crypto_ingestion_accepts_optional_video_and_audio(self):
        response = self.client.post(
            "/api/signals/channels/crypto/ingest/",
            {
                "external_id": "crypto-media-1",
                "text": "سیگنال ویدئویی کریپتو",
                "video": SimpleUploadedFile(
                    "telegram.mp4", b"video-content", content_type="video/mp4"
                ),
                "audio": SimpleUploadedFile(
                    "telegram.ogg", b"audio-content", content_type="audio/ogg"
                ),
            },
            format="multipart",
            secure=True,
            **self.ingestion_headers,
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data["video"].startswith("https://"))
        self.assertTrue(response.data["audio"].startswith("https://"))
        post = VIPSignalPost.objects.get(external_id="crypto-media-1")
        self.assertTrue(post.video.name.startswith("signals/vip/crypto/video/"))
        self.assertTrue(post.audio.name.startswith("signals/vip/crypto/audio/"))

    def test_forex_ingestion_accepts_telegram_voice_alias(self):
        response = self.client.post(
            "/api/signals/channels/forex/ingest/",
            {
                "external_id": "forex-voice-1",
                "text": "سیگنال صوتی فارکس",
                "voice": SimpleUploadedFile(
                    "voice.oga", b"voice-content", content_type="audio/ogg"
                ),
            },
            format="multipart",
            secure=True,
            **self.ingestion_headers,
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data["audio"].startswith("https://"))
        self.assertNotIn("voice", response.data)

        self.client.force_authenticate(self.user)
        feed = self.client.get("/api/signals/?channel=forex", secure=True)
        self.assertEqual(feed.status_code, 200)
        self.assertTrue(feed.data["results"][0]["audio"].startswith("https://"))
        self.assertIsNone(feed.data["results"][0]["video"])

    @override_settings(SIGNAL_CHANNEL_VIDEO_MAX_MB=1, SIGNAL_CHANNEL_AUDIO_MAX_MB=1)
    def test_ingestion_rejects_invalid_or_oversized_media_per_field(self):
        invalid_video = self.client.post(
            "/api/signals/channels/crypto/ingest/",
            {
                "text": "invalid video",
                "video": SimpleUploadedFile(
                    "video.exe", b"bad", content_type="application/octet-stream"
                ),
            },
            format="multipart",
            **self.ingestion_headers,
        )
        self.assertEqual(invalid_video.status_code, 400)
        self.assertIn("video", invalid_video.data["errors"])

        oversized_audio = self.client.post(
            "/api/signals/channels/forex/ingest/",
            {
                "text": "large voice",
                "voice": SimpleUploadedFile(
                    "voice.ogg", b"x" * (1024 * 1024 + 1), content_type="audio/ogg"
                ),
            },
            format="multipart",
            **self.ingestion_headers,
        )
        self.assertEqual(oversized_audio.status_code, 400)
        self.assertIn("voice", oversized_audio.data["errors"])

    def test_audio_and_voice_cannot_be_sent_together(self):
        response = self.client.post(
            "/api/signals/channels/crypto/ingest/",
            {
                "text": "duplicate audio fields",
                "audio": SimpleUploadedFile("audio.mp3", b"a", content_type="audio/mpeg"),
                "voice": SimpleUploadedFile("voice.ogg", b"v", content_type="audio/ogg"),
            },
            format="multipart",
            **self.ingestion_headers,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("voice", response.data["errors"])

    def test_forex_feed_is_separate(self):
        VIPSignalPost.objects.create(channel="CRYPTO", text="crypto")
        VIPSignalPost.objects.create(channel="FOREX", text="forex")
        self.client.force_authenticate(self.user)
        response = self.client.get("/api/signals/?channel=forex")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["text"] for item in response.data["results"]], ["forex"])

    def test_ingestion_requires_valid_key(self):
        response = self.client.post(
            "/api/signals/channels/crypto/ingest/", {"text": "test"}, format="json"
        )
        self.assertEqual(response.status_code, 401)

    def test_customer_feed_requires_authentication(self):
        self.assertEqual(self.client.get("/api/signals/").status_code, 401)

    def test_external_id_is_idempotent_per_channel(self):
        payload = {"external_id": "telegram-42", "text": "first"}
        first = self.client.post(
            "/api/signals/channels/crypto/ingest/", payload, format="json", **self.ingestion_headers
        )
        second = self.client.post(
            "/api/signals/channels/crypto/ingest/", payload, format="json", **self.ingestion_headers
        )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(VIPSignalPost.objects.count(), 1)

    def test_inactive_posts_are_hidden_from_customer_feed(self):
        VIPSignalPost.objects.create(channel="CRYPTO", text="hidden", is_active=False)
        self.client.force_authenticate(self.user)
        response = self.client.get("/api/signals/")
        self.assertEqual(response.data["count"], 0)

    def test_management_requires_signal_review_and_can_disable(self):
        post = VIPSignalPost.objects.create(
            channel="FOREX", text="managed", published_at=timezone.now()
        )
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get("/api/signals/manage/").status_code, 403)

        self.client.force_authenticate(self.admin)
        listing = self.client.get("/api/signals/manage/?channel=forex")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["count"], 1)
        updated = self.client.patch(
            f"/api/signals/manage/{post.pk}/", {"is_active": False}, format="json"
        )
        self.assertEqual(updated.status_code, 200)
        post.refresh_from_db()
        self.assertFalse(post.is_active)

    def test_dashboard_uses_new_channel_posts(self):
        VIPSignalPost.objects.create(channel="CRYPTO", text="dashboard post")
        self.client.force_authenticate(self.user)
        response = self.client.get("/api/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["stats"]["signals"], 1)
        self.assertEqual(response.data["data"]["recent_signals"][0]["kind"], "VIP_CHANNEL_POST")
