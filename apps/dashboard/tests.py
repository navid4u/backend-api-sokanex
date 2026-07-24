from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.articles.models import Article
from apps.chat.models import ChatRoom
from apps.livestream.models import LiveEvent
from apps.notifications.models import Notification
from apps.signals.models import (
    Direction,
    MarketType,
    Signal,
    SignalStatus,
)
from apps.videos.models import Video
from apps.wallet.models import Wallet


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

        Wallet.objects.update_or_create(
            user=self.customer,
            defaults={
                "balance": Decimal("1250.50000000"),
                "currency": "USDT",
            },
        )

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

        self.article = Article.objects.create(
            title="Published dashboard article",
            content="Article content",
            author=self.employee,
            status=Article.Status.PUBLISHED,
            published_at=timezone.now(),
        )
        self.video = Video.objects.create(
            title="Published dashboard video",
            external_url=(
                "https://video.example.com/watch"
            ),
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
            status=LiveEvent.Status.LIVE,
            created_by=self.employee,
            is_active=True,
        )
        self.upcoming_event = LiveEvent.objects.create(
            title="Dashboard upcoming event",
            starts_at=now + timedelta(days=1),
            status=LiveEvent.Status.SCHEDULED,
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
            "1250.50000000",
        )
        self.assertEqual(
            data["stats"]["wallet_currency"],
            "USDT",
        )
        self.assertEqual(
            data["stats"]["signals"],
            1,
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

        self.assertTrue(
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
        self.assertEqual(
            data["stats"]["my_signals"],
            2,
        )
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
        self.assertEqual(
            data["stats"]["pending_signals"],
            1,
        )

    def test_super_admin_has_all_capabilities(self):
        self.authenticate(self.super_admin)

        response = self.client.get(
            self.dashboard_url
        )

        capabilities = (
            response.data["data"]["capabilities"]
        )

        self.assertTrue(
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
        self.authenticate(self.customer)

        response = self.client.get(
            self.dashboard_url
        )

        data = response.data["data"]

        self.assertEqual(
            data["recent_signals"][0]["id"],
            self.approved_signal.pk,
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