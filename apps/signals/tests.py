from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.signals.models import (
    Direction,
    MarketType,
    Signal,
    SignalStatus,
)


class SignalAPITests(APITestCase):

    def setUp(self):
        password = "StrongPass123!"

        self.user = User.objects.create_user(
            username="customer",
            password=password,
            role=User.Role.USER,
        )

        self.trader = User.objects.create_user(
            username="trader",
            password=password,
            role=User.Role.TRADER,
        )

        self.other_trader = User.objects.create_user(
            username="other_trader",
            password=password,
            role=User.Role.TRADER,
        )

        self.employee = User.objects.create_user(
            username="employee",
            password=password,
            role=User.Role.EMPLOYEE,
        )

        self.approved_signal = self.create_signal(
            trader=self.other_trader,
            status_value=SignalStatus.APPROVED,
            symbol="BTCUSDT",
        )

        self.pending_signal = self.create_signal(
            trader=self.trader,
            status_value=SignalStatus.PENDING,
            symbol="ETHUSDT",
        )

    def create_signal(
        self,
        *,
        trader,
        status_value,
        symbol,
    ):
        return Signal.objects.create(
            title=f"{symbol} signal",
            symbol=symbol,
            market=MarketType.CRYPTO,
            direction=Direction.BUY,
            entry_price="100.00000000",
            stop_loss="90.00000000",
            take_profit="120.00000000",
            description="Test signal",
            status=status_value,
            created_by=trader,
        )

    def signal_payload(self):
        return {
            "title": "Gold buy signal",
            "symbol": "XAUUSD",
            "market": MarketType.GOLD,
            "direction": Direction.BUY,
            "entry_price": "2000.00000000",
            "stop_loss": "1980.00000000",
            "take_profit": "2050.00000000",
            "description": "Automated API test",
        }

    def authenticate(self, user):
        self.client.force_authenticate(
            user=user
        )

    def test_signal_list_requires_authentication(
        self
    ):
        response = self.client.get(
            reverse("signal-list-create")
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_user_only_sees_approved_signals(
        self
    ):
        self.authenticate(self.user)

        response = self.client.get(
            reverse("signal-list-create")
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        returned_ids = {
            item["id"]
            for item in response.data["results"]
        }

        self.assertIn(
            self.approved_signal.id,
            returned_ids,
        )

        self.assertNotIn(
            self.pending_signal.id,
            returned_ids,
        )

    def test_user_cannot_create_signal(self):
        self.authenticate(self.user)

        response = self.client.post(
            reverse("signal-list-create"),
            self.signal_payload(),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_trader_can_create_pending_signal(
        self
    ):
        self.authenticate(self.trader)

        response = self.client.post(
            reverse("signal-list-create"),
            self.signal_payload(),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        created_signal = Signal.objects.get(
            pk=response.data["id"]
        )

        self.assertEqual(
            created_signal.created_by,
            self.trader,
        )

        self.assertEqual(
            created_signal.status,
            SignalStatus.PENDING,
        )

    def test_trader_sees_only_own_signals(self):
        self.authenticate(self.trader)

        response = self.client.get(
            reverse("trader-signals")
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        returned_ids = {
            item["id"]
            for item in response.data["results"]
        }

        self.assertIn(
            self.pending_signal.id,
            returned_ids,
        )

        self.assertNotIn(
            self.approved_signal.id,
            returned_ids,
        )

    def test_buy_signal_price_validation(self):
        self.authenticate(self.trader)

        payload = self.signal_payload()

        payload["stop_loss"] = (
            "2100.00000000"
        )

        response = self.client.post(
            reverse("signal-list-create"),
            payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertIn(
            "prices",
            response.data["errors"],
        )

    def test_employee_can_list_pending_signals(
        self
    ):
        self.authenticate(self.employee)

        response = self.client.get(
            reverse("pending-signals")
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        returned_ids = {
            item["id"]
            for item in response.data["results"]
        }

        self.assertIn(
            self.pending_signal.id,
            returned_ids,
        )

        self.assertNotIn(
            self.approved_signal.id,
            returned_ids,
        )

    def test_employee_can_approve_signal(self):
        self.authenticate(self.employee)

        response = self.client.post(
            reverse(
                "signal-approve",
                kwargs={
                    "pk": self.pending_signal.pk
                },
            ),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.pending_signal.refresh_from_db()

        self.assertEqual(
            self.pending_signal.status,
            SignalStatus.APPROVED,
        )

        self.assertEqual(
            self.pending_signal.approved_by,
            self.employee,
        )

    def test_employee_can_reject_with_reason(
        self
    ):
        self.authenticate(self.employee)

        response = self.client.post(
            reverse(
                "signal-reject",
                kwargs={
                    "pk": self.pending_signal.pk
                },
            ),
            {
                "reason": "Risk is too high.",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.pending_signal.refresh_from_db()

        self.assertEqual(
            self.pending_signal.status,
            SignalStatus.REJECTED,
        )

        self.assertEqual(
            self.pending_signal.rejection_reason,
            "Risk is too high.",
        )

        self.assertEqual(
            self.pending_signal.approved_by,
            self.employee,
        )

    def test_reject_requires_reason(self):
        self.authenticate(self.employee)

        response = self.client.post(
            reverse(
                "signal-reject",
                kwargs={
                    "pk": self.pending_signal.pk
                },
            ),
            {
                "reason": "",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertIn(
            "reason",
            response.data["errors"],
        )

    def test_trader_cannot_approve_signal(self):
        self.authenticate(self.trader)

        response = self.client.post(
            reverse(
                "signal-approve",
                kwargs={
                    "pk": self.pending_signal.pk
                },
            ),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_user_cannot_open_pending_detail(
        self
    ):
        self.authenticate(self.user)

        response = self.client.get(
            reverse(
                "signal-detail",
                kwargs={
                    "pk": self.pending_signal.pk
                },
            )
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )