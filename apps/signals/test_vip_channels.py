import base64
import json
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from datetime import timedelta
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
        now = timezone.now()
        self.user = User.objects.create_user(
            username="viewer", password="pass", access_level=User.AccessLevel.LEVEL_5,
            gold_trial_started_at=now, gold_trial_expires_at=now + timedelta(days=7),
        )
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

    def test_forex_market_type_is_default_but_explicit_channel_wins(self):
        VIPSignalPost.objects.create(channel="CRYPTO", text="کریپتو")
        VIPSignalPost.objects.create(channel="FOREX", text="فارکس")
        self.user.market_type = User.MarketType.FOREX
        self.user.save(update_fields=("market_type",))
        self.client.force_authenticate(self.user)

        default_feed = self.client.get("/api/signals/")
        self.assertEqual(default_feed.status_code, 200)
        self.assertEqual(default_feed.data["count"], 1)
        self.assertEqual(default_feed.data["results"][0]["channel"], "FOREX")

        crypto_feed = self.client.get("/api/signals/?channel=crypto")
        self.assertEqual(crypto_feed.status_code, 200)
        self.assertEqual(crypto_feed.data["results"][0]["channel"], "CRYPTO")

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

    def test_expired_trial_cannot_read_vip_feed_or_detail(self):
        post = VIPSignalPost.objects.create(channel="CRYPTO", text="gold-only")
        User.objects.filter(pk=self.user.pk).update(
            access_level=User.AccessLevel.LEVEL_2,
            gold_trial_started_at=timezone.now() - timedelta(days=8),
            gold_trial_expires_at=timezone.now() - timedelta(days=1),
        )
        self.user.refresh_from_db()
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get("/api/signals/").status_code, 403)
        self.assertEqual(self.client.get(f"/api/signals/{post.pk}/").status_code, 403)

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

    def test_reply_links_and_previews_parent_in_both_markets(self):
        for channel in ("crypto", "forex"):
            with self.subTest(channel=channel):
                ingest = f"/api/signals/channels/{channel}/ingest/"
                parent_id = f"telegram:{channel}:10"
                parent = self.client.post(
                    ingest, {"external_id": parent_id, "text": "پیام مرجع"},
                    format="json", **self.ingestion_headers,
                )
                reply = self.client.post(
                    ingest,
                    {
                        "external_id": f"telegram:{channel}:11",
                        "reply_to_external_id": parent_id,
                        "text": "پاسخ به مرجع",
                    },
                    format="json", **self.ingestion_headers,
                )
                self.assertEqual(reply.status_code, 201, reply.data)
                self.assertEqual(reply.data["reply_preview"]["id"], parent.data["id"])
                self.assertEqual(reply.data["reply_preview"]["text"], "پیام مرجع")
                self.client.force_authenticate(self.user)
                detail = self.client.get(f"/api/signals/{reply.data['id']}/")
                feed = self.client.get(f"/api/signals/?channel={channel}")
                self.assertEqual(detail.data["reply_preview"]["id"], parent.data["id"])
                self.assertEqual(feed.data["results"][0]["reply_preview"]["id"], parent.data["id"])
                self.client.force_authenticate(user=None)

    def test_out_of_order_reply_resolves_and_preserves_safe_snapshot(self):
        ingest = "/api/signals/channels/crypto/ingest/"
        payload = {
            "external_id": "telegram:crypto:21",
            "reply_to_external_id": "telegram:crypto:20",
            "reply_snapshot": {"text": "<b>نقل قول</b>", "media_type": "image"},
            "text": "جواب",
        }
        reply = self.client.post(ingest, payload, format="json", **self.ingestion_headers)
        self.assertEqual(reply.status_code, 201, reply.data)
        self.assertIsNone(reply.data["reply_preview"]["id"])
        self.assertEqual(reply.data["reply_preview"]["text"], "نقل قول")
        self.assertFalse(reply.data["reply_preview"]["available"])
        parent = self.client.post(
            ingest,
            {"external_id": "telegram:crypto:20", "text": "متن کامل مرجع"},
            format="json", **self.ingestion_headers,
        )
        self.assertEqual(parent.status_code, 201, parent.data)
        self.client.force_authenticate(self.user)
        detail = self.client.get(f"/api/signals/{reply.data['id']}/")
        self.assertEqual(detail.data["reply_preview"]["id"], parent.data["id"])
        self.assertTrue(detail.data["reply_preview"]["available"])

    def test_retry_preserves_reply_and_rejects_changed_reference(self):
        ingest = "/api/signals/channels/forex/ingest/"
        payload = {
            "external_id": "telegram:forex:31",
            "reply_to_external_id": "telegram:forex:30",
            "reply_snapshot": {"text": "مرجع قدیمی"},
            "text": "پاسخ",
        }
        first = self.client.post(ingest, payload, format="json", **self.ingestion_headers)
        self.assertEqual(first.status_code, 201, first.data)
        retry = self.client.post(
            ingest, {"external_id": payload["external_id"], "text": "retry"},
            format="json", **self.ingestion_headers,
        )
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.data["reply_to_external_id"], payload["reply_to_external_id"])
        self.assertEqual(retry.data["reply_preview"]["text"], "مرجع قدیمی")
        conflict = self.client.post(
            ingest, {**payload, "reply_to_external_id": "telegram:forex:29"},
            format="json", **self.ingestion_headers,
        )
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(VIPSignalPost.objects.filter(external_id=payload["external_id"]).count(), 1)

    def test_retry_can_attach_reply_to_preexisting_post(self):
        ingest = "/api/signals/channels/forex/ingest/"
        self.assertEqual(self.client.post(
            ingest, {"external_id": "telegram:forex:70", "text": "مرجع قدیمی"},
            format="json", **self.ingestion_headers,
        ).status_code, 201)
        old_reply = self.client.post(
            ingest, {"external_id": "telegram:forex:71", "text": "پاسخ قدیمی"},
            format="json", **self.ingestion_headers,
        )
        attached = self.client.post(
            ingest, {
                "external_id": "telegram:forex:71",
                "reply_to_external_id": "telegram:forex:70",
                "text": "پاسخ قدیمی",
            }, format="json", **self.ingestion_headers,
        )
        self.assertEqual(attached.status_code, 200, attached.data)
        self.assertEqual(attached.data["id"], old_reply.data["id"])
        self.assertIsNotNone(attached.data["reply_preview"]["id"])

    def test_multipart_reply_snapshot_is_sanitized(self):
        response = self.client.post(
            "/api/signals/channels/crypto/ingest/",
            {
                "external_id": "telegram:crypto:81",
                "reply_to_external_id": "telegram:crypto:80",
                "reply_snapshot": json.dumps({"text": "<script>bad()</script><b>مرجع</b>"}),
                "text": "پاسخ",
            }, format="multipart", **self.ingestion_headers,
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertNotIn("<", response.data["reply_preview"]["text"])

    def test_deleted_or_inactive_parent_uses_snapshot_without_link(self):
        ingest = "/api/signals/channels/crypto/ingest/"
        parent = self.client.post(
            ingest, {"external_id": "telegram:crypto:40", "text": "مرجع ذخیره شده"},
            format="json", **self.ingestion_headers,
        )
        reply = self.client.post(
            ingest, {
                "external_id": "telegram:crypto:41",
                "reply_to_external_id": "telegram:crypto:40",
                "text": "پاسخ",
            }, format="json", **self.ingestion_headers,
        )
        VIPSignalPost.objects.filter(pk=parent.data["id"]).update(is_active=False)
        self.client.force_authenticate(self.user)
        hidden = self.client.get(f"/api/signals/{reply.data['id']}/")
        self.assertIsNone(hidden.data["reply_preview"]["id"])
        self.assertEqual(hidden.data["reply_preview"]["text"], "مرجع ذخیره شده")
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.delete(f"/api/signals/manage/{parent.data['id']}/").status_code, 204)
        self.client.force_authenticate(self.user)
        deleted = self.client.get(f"/api/signals/{reply.data['id']}/")
        self.assertIsNone(deleted.data["reply_preview"]["id"])
        self.assertEqual(deleted.data["reply_preview"]["text"], "مرجع ذخیره شده")

    def test_cross_market_self_reply_and_cycle_are_rejected(self):
        crypto = "/api/signals/channels/crypto/ingest/"
        forex = "/api/signals/channels/forex/ingest/"
        self.assertEqual(self.client.post(
            crypto, {"external_id": "telegram:crypto:50", "text": "کریپتو"},
            format="json", **self.ingestion_headers,
        ).status_code, 201)
        cross = self.client.post(
            forex, {
                "external_id": "telegram:forex:51",
                "reply_to_external_id": "telegram:crypto:50", "text": "فارکس",
            }, format="json", **self.ingestion_headers,
        )
        self.assertEqual(cross.status_code, 400)
        self.assertIn("reply_to_external_id", cross.data["errors"])
        self_reply = self.client.post(
            crypto, {
                "external_id": "telegram:crypto:52",
                "reply_to_external_id": "telegram:crypto:52", "text": "خودش",
            }, format="json", **self.ingestion_headers,
        )
        self.assertEqual(self_reply.status_code, 400)
        self.assertEqual(self.client.post(
            crypto, {
                "external_id": "telegram:crypto:60",
                "reply_to_external_id": "telegram:crypto:61", "text": "A",
            }, format="json", **self.ingestion_headers,
        ).status_code, 201)
        cycle = self.client.post(
            crypto, {
                "external_id": "telegram:crypto:61",
                "reply_to_external_id": "telegram:crypto:60", "text": "B",
            }, format="json", **self.ingestion_headers,
        )
        self.assertEqual(cycle.status_code, 400)
        self.assertIn("reply_to_external_id", cycle.data["errors"])

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
