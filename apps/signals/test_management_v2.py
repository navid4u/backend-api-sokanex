from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import PlatformRole, User
from .models import Signal, SignalStatus


class SignalManagementV2Tests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="signal-admin", password="StrongPass123!", role=User.Role.ADMIN)
        self.trader = User.objects.create_user(username="signal-trader", password="StrongPass123!", role=User.Role.TRADER)
        self.other_trader = User.objects.create_user(username="other-trader", password="StrongPass123!", role=User.Role.TRADER)
        self.employee = User.objects.create_user(username="signal-employee", password="StrongPass123!", role=User.Role.EMPLOYEE)
        self.user = User.objects.create_user(username="signal-user", password="StrongPass123!", role=User.Role.USER)
        self.submit_role = PlatformRole.objects.create(
            name="Signal submitter", slug="signal-submitter", permissions=[User.Permission.SIGNAL_SUBMIT], created_by=self.admin,
        )
        self.review_role = PlatformRole.objects.create(
            name="Signal reviewer", slug="signal-reviewer", permissions=[User.Permission.SIGNAL_REVIEW], created_by=self.admin,
        )
        self.custom_submitter = User.objects.create_user(
            username="custom-submitter", password="StrongPass123!", role=User.Role.USER, custom_role=self.submit_role,
        )
        self.custom_reviewer = User.objects.create_user(
            username="custom-reviewer", password="StrongPass123!", role=User.Role.USER, custom_role=self.review_role,
        )
        self.payload = {
            "title": "Gold setup", "symbol": "XAUUSD", "market": "gold", "direction": "buy",
            "entry_price": "2000", "stop_loss": "1990", "take_profit": "2020",
            "description": "Managed signal", "allowed_levels": [1, 2, 3, 4, 5],
        }

    def authenticate(self, user):
        self.client.force_authenticate(user)

    def create_for(self, user, **overrides):
        return Signal.objects.create(
            title=overrides.get("title", "Signal"), symbol=overrides.get("symbol", "EURUSD"),
            market="forex", direction="buy", entry_price=Decimal("1.10000000"),
            stop_loss=Decimal("1.00000000"), take_profit=Decimal("1.20000000"),
            status=overrides.get("status", SignalStatus.PENDING), created_by=user,
            rejection_reason=overrides.get("rejection_reason", ""),
        )

    def test_admin_and_custom_submitter_can_submit(self):
        for actor in (self.admin, self.custom_submitter, self.trader):
            self.authenticate(actor)
            response = self.client.post(reverse("signal-list-create"), self.payload, format="json")
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            self.assertEqual(Signal.objects.latest("id").created_by, actor)

    def test_employee_without_submit_permission_cannot_submit(self):
        self.authenticate(self.employee)
        response = self.client.post(reverse("signal-list-create"), self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_my_signals_only_contains_owner_rows(self):
        own = self.create_for(self.trader, title="Mine")
        self.create_for(self.other_trader, title="Other")
        self.authenticate(self.trader)
        response = self.client.get(reverse("trader-signals"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([row["id"] for row in response.data["results"]], [own.id])

    def test_reviewers_can_manage_and_regular_user_cannot(self):
        self.create_for(self.trader)
        for actor in (self.admin, self.employee, self.custom_reviewer):
            self.authenticate(actor)
            self.assertEqual(self.client.get(reverse("signal-management-list")).status_code, 200)
            self.assertEqual(self.client.get(reverse("pending-signals")).status_code, 200)
        self.authenticate(self.user)
        self.assertEqual(self.client.get(reverse("signal-management-list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("pending-signals")).status_code, 403)

    def test_manage_returns_all_statuses_summary_filters_and_rejection_reason(self):
        self.create_for(self.trader, status=SignalStatus.PENDING)
        self.create_for(self.trader, status=SignalStatus.APPROVED)
        rejected = self.create_for(self.trader, status=SignalStatus.REJECTED, rejection_reason="Invalid analysis")
        self.create_for(self.trader, status=SignalStatus.DRAFT)
        self.authenticate(self.admin)
        response = self.client.get(reverse("signal-management-list"), {"page_size": 100})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 4)
        self.assertEqual(response.data["summary"]["pending"], 1)
        rejected_row = next(row for row in response.data["results"] if row["id"] == rejected.id)
        self.assertEqual(rejected_row["rejection_reason"], "Invalid analysis")
        self.assertEqual(rejected_row["trader_id"], self.trader.id)

    def test_approve_reject_and_result_labels(self):
        approved = self.create_for(self.trader)
        rejected = self.create_for(self.trader)
        self.authenticate(self.employee)
        self.assertEqual(self.client.post(reverse("signal-approve", kwargs={"pk": approved.pk})).status_code, 200)
        self.assertEqual(
            self.client.post(reverse("signal-reject", kwargs={"pk": rejected.pk}), {"reason": "Bad entry"}, format="json").status_code,
            200,
        )
        approved.refresh_from_db()
        rejected.refresh_from_db()
        self.assertEqual(approved.status, SignalStatus.APPROVED)
        self.assertEqual(rejected.status, SignalStatus.REJECTED)
        result = self.client.patch(
            reverse("signal-detail", kwargs={"pk": approved.pk}),
            {"status": SignalStatus.SUCCESSFUL, "result_price": "2020", "result_percent": "1.5"}, format="json",
        )
        self.assertEqual(result.status_code, 200)
        approved.refresh_from_db()
        self.assertEqual(approved.status, SignalStatus.SUCCESSFUL)
        self.assertIsNotNone(approved.closed_at)
        self.assertTrue(approved.updates.filter(status=SignalStatus.SUCCESSFUL).exists())
