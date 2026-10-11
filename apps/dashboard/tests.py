from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.accounts.models import UserMarketGrant
from apps.content_channels.models import Channel, ChannelPost
from apps.articles.models import Article
from apps.chat.models import ChatRoom
from apps.livestream.models import LiveEvent
from apps.notifications.models import Notification
from apps.signals.models import (
    Direction,
    MarketType,
    Signal,
    SignalStatus,
    VIPSignalPost,
)
from apps.videos.models import Video
from apps.wallet.models import Wallet
from apps.wallet.services import WalletService


class DashboardAPITests(APITestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            username="dashboard_customer",
            email="dashboard_customer@example.com",
            password="StrongPass123!",
            role=User.Role.USER,
        )
        self.trader = User.objects.create_user(
            username="dashboard_trader",
            email="dashboard_trader@example.com",
            password="StrongPass123!",
            role=User.Role.TRADER,
        )
        self.employee = User.objects.create_user(
            username="dashboard_employee",
            email="dashboard_employee@example.com",
            password="StrongPass123!",
            role=User.Role.EMPLOYEE,
        )
        self.super_admin = User.objects.create_user(
            username="dashboard_super_admin",
            email="dashboard_super_admin@example.com",
            password="StrongPass123!",
            role=User.Role.SUPER_ADMIN,
        )

        wallet, _ = Wallet.objects.update_or_create(
            user=self.customer,
            defaults={"currency": "IRT"},
        )
        WalletService.post(wallet, 1250, "TEST_OPENING_BALANCE")

        self.approved_signal = Signal.objects.create(
            title="Approved BTC signal",
            symbol="BTCUSDT",
            market=MarketType.CRYPTO,
            direction=Direction.BUY,
            entry_price=Decimal("60000"),
            stop_loss=Decimal("59000"),
            take_profit=Decimal("62000"),
            status=SignalStatus.APPROVED,
            created_by=self.trader,
            approved_by=self.employee,
        )
        self.pending_signal = Signal.objects.create(
            title="Pending EURUSD signal",
            symbol="EURUSD",
            market=MarketType.FOREX,
            direction=Direction.SELL,
            entry_price=Decimal("1.10000000"),
            stop_loss=Decimal("1.11000000"),
            take_profit=Decimal("1.08000000"),
            status=SignalStatus.PENDING,
            created_by=self.trader,
        )
        self.vip_signal = VIPSignalPost.objects.create(
            channel=VIPSignalPost.Channel.CRYPTO,
            text="Published VIP crypto channel post",
        )

        self.article = Article.objects.create(
            title="Published dashboard article",
            content="Article content",
            author=self.employee,
            status=Article.Status.PUBLISHED,
            published_at=timezone.now(),
        )
        self.video = Video.objects.create(
            title="Published dashboard video",
            external_url="https://video.example.com/watch",
            author=self.employee,
            status=Video.Status.PUBLISHED,
            published_at=timezone.now(),
        )
        self.notification = Notification.objects.create(
            title="Dashboard notification",
            message="Visible notification",
            created_by=self.employee,
            is_active=True,
        )
        self.chat_room = ChatRoom.objects.create(
            name="Dashboard public chat",
            is_public=True,
            is_active=True,
            created_by=self.employee,
        )

        now = timezone.now()

        self.live_event = LiveEvent.objects.create(
            title="Dashboard live event",
            stream_url="https://stream.example.com/live",
            starts_at=now - timedelta(minutes=10),
            ends_at=now + timedelta(minutes=50),
            status=LiveEvent.Status.ACTIVE,
            created_by=self.employee,
            is_active=True,
        )
        self.upcoming_event = LiveEvent.objects.create(
            title="Dashboard upcoming event",
            starts_at=now + timedelta(days=1),
            status=LiveEvent.Status.UPCOMING,
            created_by=self.employee,
            is_active=True,
        )

        self.dashboard_url = reverse("dashboard")

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def test_dashboard_requires_authentication(self):
        response = self.client.get(
            self.dashboard_url
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_customer_dashboard_contains_expected_data(self):
        self.authenticate(self.customer)

        response = self.client.get(
            self.dashboard_url
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertTrue(
            response.data["success"]
        )

        data = response.data["data"]

        self.assertEqual(
            data["user"]["username"],
            self.customer.username,
        )
        self.assertEqual(
            data["stats"]["wallet_balance"],
            "1250.00000000",
        )
        self.assertEqual(
            data["stats"]["wallet_currency"],
            "IRT",
        )
        self.assertEqual(
            data["stats"]["signals"],
            0,
        )
        self.assertEqual(
            data["stats"]["articles"],
            1,
        )
        self.assertEqual(
            data["stats"]["videos"],
            1,
        )
        self.assertEqual(
            data["stats"]["notifications"],
            1,
        )
        self.assertEqual(
            data["stats"]["chat_rooms"],
            1,
        )
        self.assertEqual(
            data["stats"]["live_events"],
            1,
        )
        self.assertEqual(
            data["stats"]["upcoming_live_events"],
            1,
        )
        self.assertEqual(
            data["stats"]["unread_notifications"],
            1,
        )

    def test_customer_has_only_public_capabilities(self):
        self.authenticate(self.customer)

        response = self.client.get(
            self.dashboard_url
        )

        capabilities = (
            response.data["data"]["capabilities"]
        )

        self.assertFalse(
            capabilities["can_submit_signals"]
        )
        self.assertFalse(
            capabilities["can_review_signals"]
        )
        self.assertFalse(
            capabilities["can_manage_content"]
        )
        self.assertFalse(
            capabilities["can_manage_users"]
        )

    def test_trader_can_submit_but_cannot_review_signals(self):
        self.authenticate(self.trader)

        response = self.client.get(
            self.dashboard_url
        )

        data = response.data["data"]
        capabilities = data["capabilities"]

        self.assertFalse(
            capabilities["can_submit_signals"]
        )
        self.assertFalse(
            capabilities["can_review_signals"]
        )
        self.assertFalse(
            capabilities["can_manage_content"]
        )
        self.assertFalse(
            capabilities["can_manage_users"]
        )
        self.assertEqual(data["stats"]["my_signals"], 0)
        self.assertEqual(
            data["stats"]["pending_signals"],
            0,
        )

    def test_employee_can_review_and_manage_content(self):
        self.authenticate(self.employee)

        response = self.client.get(
            self.dashboard_url
        )

        data = response.data["data"]
        capabilities = data["capabilities"]

        self.assertFalse(
            capabilities["can_submit_signals"]
        )
        self.assertTrue(
            capabilities["can_review_signals"]
        )
        self.assertTrue(
            capabilities["can_manage_content"]
        )
        self.assertFalse(
            capabilities["can_manage_users"]
        )
        self.assertEqual(data["stats"]["pending_signals"], 0)

    def test_super_admin_has_all_capabilities(self):
        self.authenticate(self.super_admin)

        response = self.client.get(
            self.dashboard_url
        )

        capabilities = (
            response.data["data"]["capabilities"]
        )

        self.assertFalse(
            capabilities["can_submit_signals"]
        )
        self.assertTrue(
            capabilities["can_review_signals"]
        )
        self.assertTrue(
            capabilities["can_manage_content"]
        )
        self.assertTrue(
            capabilities["can_manage_users"]
        )

    def test_dashboard_contains_recent_collections(self):
        now = timezone.now()
        User.objects.filter(pk=self.customer.pk).update(
            access_level=User.AccessLevel.LEVEL_5,
            gold_trial_started_at=now,
            gold_trial_expires_at=now + timedelta(days=7),
        )
        self.customer.refresh_from_db()
        self.authenticate(self.customer)

        response = self.client.get(
            self.dashboard_url
        )

        data = response.data["data"]

        self.assertEqual(
            data["recent_signals"][0]["id"],
            self.vip_signal.pk,
        )
        self.assertEqual(
            data["recent_articles"][0]["id"],
            self.article.pk,
        )
        self.assertEqual(
            data["recent_videos"][0]["id"],
            self.video.pk,
        )
        self.assertEqual(
            data["recent_notifications"][0]["id"],
            self.notification.pk,
        )
        self.assertEqual(
            data["chat_rooms"][0]["id"],
            self.chat_room.pk,
        )
        self.assertEqual(
            data["live_events"][0]["id"],
            self.live_event.pk,
        )
        self.assertEqual(
            data["upcoming_live_events"][0]["id"],
            self.upcoming_event.pk,
        )

    def test_dashboard_does_not_leak_vip_signal_posts_after_trial_expiry(self):
        now = timezone.now()
        User.objects.filter(pk=self.customer.pk).update(
            access_level=User.AccessLevel.LEVEL_2,
            gold_trial_started_at=now - timedelta(days=8),
            gold_trial_expires_at=now - timedelta(seconds=1),
        )
        self.customer.refresh_from_db()
        self.authenticate(self.customer)
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertEqual(data["stats"]["signals"], 0)
        self.assertEqual(data["recent_signals"], [])

    def _make_internal_post(self, scope, title, body, published_at=None, status=ChannelPost.Status.PUBLISHED):
        channel, _ = Channel.objects.get_or_create(slug="internal-analysis", defaults={"name": "Internal"})
        return ChannelPost.objects.create(
            channel=channel, title=title, body=body, scope=scope,
            author=self.employee, status=status,
            published_at=published_at or timezone.now(),
        )

    @override_settings(MARKET_ACCESS_V2_ENABLED=True)
    def test_locked_previews_include_only_public_projection_and_filter_feeds(self):
        now = timezone.now()
        private = "PRIVATE_ENTRY_9988 " * 30
        self.vip_signal.text = private
        self.vip_signal.image = "signals/private-secret-image.png"
        self.vip_signal.published_at = now
        self.vip_signal.save()
        newer = VIPSignalPost.objects.create(channel="FOREX", text="secret forex", published_at=now)
        inactive = VIPSignalPost.objects.create(channel="CRYPTO", text="inactive", is_active=False, published_at=now + timedelta(hours=1))
        internal = self._make_internal_post("GOLD", "Gold opportunity", private, now)
        internal.image = "channels/private-analysis-image.png"
        internal.save(update_fields=["image"])
        self._make_internal_post("FOREX", "Forex excluded", "forex", now + timedelta(hours=1))
        self._make_internal_post("GOLD", "Draft excluded", "draft", now, ChannelPost.Status.DRAFT)
        self._make_internal_post("STOCK", "Future excluded", "future", now + timedelta(hours=1))
        self.authenticate(self.customer)
        data = self.client.get(self.dashboard_url).data["data"]
        previews = data["vip_signal_previews"]
        self.assertEqual([p["id"] for p in previews], [newer.pk, self.vip_signal.pk])
        self.assertTrue(all(not p["can_view"] and p["image"] is None for p in previews))
        self.assertEqual([p["id"] for p in data["recent_internal_analysis"]], [internal.pk])
        self.assertFalse(data["recent_internal_analysis"][0]["can_view"])
        self.assertNotIn(private, str(data))
        self.assertNotIn("private-secret-image", str(data))
        self.assertNotIn("private-analysis-image", str(data))
        self.assertNotIn(inactive.pk, [p["id"] for p in previews])
        self.assertEqual(self.client.get("/api/signals/").status_code, 403)
        self.assertEqual(self.client.get("/api/channels/internal-analysis/").status_code, 403)

    @override_settings(MARKET_ACCESS_V2_ENABLED=True)
    def test_v2_market_grants_and_admin_previews(self):
        VIPSignalPost.objects.create(channel="FOREX", text="Forex post")
        for market in ("crypto", "forex", "internal"):
            UserMarketGrant.objects.create(user=self.customer, market=market, source=UserMarketGrant.Source.ADMIN)
        self.authenticate(self.customer)
        data = self.client.get(self.dashboard_url).data["data"]
        self.assertEqual({p["channel"] for p in data["vip_signal_previews"] if p["can_view"]}, {"CRYPTO", "FOREX"})
        self.authenticate(self.super_admin)
        admin_data = self.client.get(self.dashboard_url).data["data"]
        self.assertTrue(all(p["can_view"] for p in admin_data["vip_signal_previews"]))

    @override_settings(MARKET_ACCESS_V2_ENABLED=True)
    def test_single_market_grants_do_not_bypass_gold_gate(self):
        VIPSignalPost.objects.create(channel="FOREX", text="Forex private body")
        for market in ("crypto", "forex"):
            with self.subTest(market=market):
                UserMarketGrant.objects.filter(user=self.customer).delete()
                UserMarketGrant.objects.create(user=self.customer, market=market, source=UserMarketGrant.Source.ADMIN)
                self.authenticate(self.customer)
                data = self.client.get(self.dashboard_url).data["data"]
                self.assertTrue(all(not post["can_view"] for post in data["vip_signal_previews"]))
                self.assertNotIn("Forex private body", str(data))

    @override_settings(MARKET_ACCESS_V2_ENABLED=False)
    def test_legacy_gold_preview_is_viewable(self):
        self.customer.access_level = User.AccessLevel.LEVEL_5
        self.customer.gold_trial_started_at = timezone.now()
        self.customer.gold_trial_expires_at = timezone.now() + timedelta(days=7)
        self.customer.save(update_fields=["access_level", "gold_trial_started_at", "gold_trial_expires_at"])
        self.authenticate(self.customer)
        data = self.client.get(self.dashboard_url).data["data"]
        self.assertTrue(data["vip_signal_previews"][0]["can_view"])

    @override_settings(MARKET_ACCESS_V2_ENABLED=False)
    def test_legacy_level_one_preview_remains_locked(self):
        self.authenticate(self.customer)
        data = self.client.get(self.dashboard_url).data["data"]
        self.assertFalse(data["vip_signal_previews"][0]["can_view"])

    def test_preview_limits_and_deterministic_order(self):
        now = timezone.now()
        for index in range(6):
            VIPSignalPost.objects.create(channel="CRYPTO", text=str(index), published_at=now)
            self._make_internal_post("GOLD", f"Gold {index}", "Body", now)
        self.authenticate(self.customer)
        data = self.client.get(self.dashboard_url).data["data"]
        self.assertEqual(len(data["vip_signal_previews"]), 4)
        self.assertEqual(len(data["recent_internal_analysis"]), 3)
        self.assertEqual([p["id"] for p in data["vip_signal_previews"]], sorted([p["id"] for p in data["vip_signal_previews"]], reverse=True))

    def test_inactive_internal_channel_is_not_previewed(self):
        self._make_internal_post("GOLD", "Hidden", "Private")
        Channel.objects.filter(slug="internal-analysis").update(is_active=False)
        self.authenticate(self.customer)
        self.assertEqual(self.client.get(self.dashboard_url).data["data"]["recent_internal_analysis"], [])
