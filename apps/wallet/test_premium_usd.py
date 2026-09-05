from decimal import Decimal
from unittest.mock import patch

from django.db import connection
from django.test import TransactionTestCase
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import UpgradeRequest, User, UserProfile
from .models import LedgerEntry, UpgradePlan, UsdLedgerEntry, Wallet
from .services import WalletService


class PremiumUsdAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="premium-user", password="pass")
        self.wallet = WalletService.get_wallet(self.user)
        self.plan = UpgradePlan.objects.get(level=5)
        self.plan.active = True
        self.plan.price_usd = Decimal("100.00")
        self.plan.save(update_fields=["active", "price_usd"])
        self.client.force_authenticate(self.user)
        self.url = "/api/accounts/upgrade-requests/premium/purchase/"

    def test_welcome_credit_is_created_exactly_once(self):
        self.assertEqual(self.wallet.balance_usd, Decimal("100.00"))
        self.assertEqual(
            UsdLedgerEntry.objects.filter(
                wallet=self.wallet, idempotency_key="WELCOME_CREDIT"
            ).count(),
            1,
        )
        WalletService.get_wallet(self.user)
        self.assertEqual(
            UsdLedgerEntry.objects.filter(
                wallet=self.wallet, idempotency_key="WELCOME_CREDIT"
            ).count(),
            1,
        )

    def test_plan_management_updates_same_premium_plan_price(self):
        manager = User.objects.create_superuser(username="premium-admin", password="pass")
        self.client.force_authenticate(manager)
        response = self.client.patch(
            f"/api/admin/platform/upgrade-plans/{self.plan.pk}/",
            {"price_usd": "75.50"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.price_usd, Decimal("75.50"))
        self.assertEqual(self.plan.plan_type, UpgradePlan.Type.PREMIUM)
        self.client.force_authenticate(self.user)
        purchased = self.client.post(
            self.url, {"idempotency_key": "purchase-managed-price"}, format="json"
        )
        self.assertEqual(purchased.status_code, 201)
        self.assertEqual(purchased.data["wallet"]["balance_usd"], "24.50")

    def test_successful_purchase_uses_server_price_and_activates_level_five(self):
        response = self.client.post(
            self.url,
            {"idempotency_key": "purchase-success-1", "plan_id": self.plan.pk, "amount_usd": "1.00"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["wallet"]["balance_usd"], "0.00")
        self.assertTrue(response.data["subscription"]["active"])
        self.assertEqual(response.data["subscription"]["tier"], "GOLD")
        self.user.refresh_from_db()
        self.assertEqual(self.user.access_level, 5)
        purchase = UpgradeRequest.objects.get(user=self.user, request_type="PREMIUM")
        self.assertEqual(purchase.status, UpgradeRequest.Status.APPROVED)
        self.assertEqual(purchase.price_snapshot_usd, Decimal("100.00"))
        self.assertEqual(
            UsdLedgerEntry.objects.filter(wallet=self.wallet, kind="PREMIUM_PURCHASE").count(), 1
        )

    def test_insufficient_balance_is_402_and_atomic(self):
        self.wallet.balance_usd = Decimal("99.00")
        self.wallet.save(update_fields=["balance_usd"])
        response = self.client.post(
            self.url, {"idempotency_key": "purchase-low-balance"}, format="json"
        )
        self.assertEqual(response.status_code, 402)
        self.assertEqual(response.data["error_code"], "INSUFFICIENT_BALANCE")
        self.assertEqual(response.data["required_usd"], "100.00")
        self.assertEqual(response.data["balance_usd"], "99.00")
        self.assertFalse(UpgradeRequest.objects.filter(user=self.user).exists())
        self.assertFalse(UsdLedgerEntry.objects.filter(wallet=self.wallet, kind="PREMIUM_PURCHASE").exists())

    def test_purchase_is_idempotent_and_active_subscription_does_not_debit_again(self):
        payload = {"idempotency_key": "purchase-repeat-1", "plan_id": self.plan.pk}
        first = self.client.post(self.url, payload, format="json")
        second = self.client.post(self.url, payload, format="json")
        third = self.client.post(
            self.url, {"idempotency_key": "purchase-another-click"}, format="json"
        )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(third.status_code, 200)
        self.assertEqual(UpgradeRequest.objects.filter(user=self.user, request_type="PREMIUM").count(), 1)
        self.assertEqual(UsdLedgerEntry.objects.filter(wallet=self.wallet, kind="PREMIUM_PURCHASE").count(), 1)

    def test_existing_pending_premium_request_is_finalized_not_duplicated(self):
        pending = UpgradeRequest.objects.create(
            user=self.user,
            request_type=UpgradeRequest.Type.PREMIUM,
            requested_level=5,
            plan=self.plan,
        )
        response = self.client.post(
            self.url, {"idempotency_key": "purchase-pending-request"}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        pending.refresh_from_db()
        self.assertEqual(pending.status, UpgradeRequest.Status.APPROVED)
        self.assertEqual(pending.purchase_idempotency_key, "purchase-pending-request")
        self.assertEqual(UpgradeRequest.objects.filter(user=self.user).count(), 1)

    def test_purchase_requires_authentication(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(
            self.url, {"idempotency_key": "purchase-no-auth"}, format="json"
        )
        self.assertEqual(response.status_code, 401)

    def test_failure_rolls_back_balance_and_preserves_toman_ledger(self):
        WalletService.post(self.wallet, 5000, "TEST_IRT_CREDIT")
        toman_entries = LedgerEntry.objects.filter(wallet=self.wallet).count()
        with patch("apps.wallet.services.UsdLedgerEntry.objects.create", side_effect=RuntimeError("db")):
            with self.assertRaises(RuntimeError):
                WalletService.purchase_premium(self.user, "purchase-rollback")
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_usd, Decimal("100.00"))
        self.assertEqual(LedgerEntry.objects.filter(wallet=self.wallet).count(), toman_entries)
        self.assertFalse(UpgradeRequest.objects.filter(user=self.user).exists())

    def test_wallet_dashboard_and_profile_expose_usd_and_subscription(self):
        wallet_response = self.client.get("/api/wallet/")
        dashboard_response = self.client.get("/api/dashboard/")
        UserProfile.objects.get_or_create(user=self.user)
        profile_response = self.client.get("/api/accounts/profile/details/")
        self.assertEqual(wallet_response.status_code, 200)
        self.assertEqual(wallet_response.data["balance_usd"], "100.00")
        self.assertEqual(wallet_response.data["display_currency"], "USD")
        dashboard = dashboard_response.data.get("data", dashboard_response.data)
        self.assertEqual(dashboard["stats"]["wallet_balance_usd"], "100.00")
        self.assertIn("premium_subscription", dashboard)
        self.assertEqual(profile_response.data["wallet_balance_usd"], "100.00")
        self.assertIn("premium_subscription", profile_response.data)


class PremiumPurchaseConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def test_concurrent_purchase_creates_one_debit(self):
        if connection.vendor == "sqlite":
            self.skipTest("Row-lock concurrency is verified on PostgreSQL, not SQLite.")
        from concurrent.futures import ThreadPoolExecutor

        user = User.objects.create_user(username="premium-concurrent", password="pass")
        WalletService.get_wallet(user)
        plan = UpgradePlan.objects.get(level=5)
        plan.active = True
        plan.price_usd = Decimal("100.00")
        plan.save(update_fields=["active", "price_usd"])

        def purchase():
            local_user = User.objects.get(pk=user.pk)
            return WalletService.purchase_premium(local_user, "same-concurrent-key")[2]

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: purchase(), range(2)))
        self.assertEqual(results.count(True), 1)
        self.assertEqual(UpgradeRequest.objects.filter(user=user, request_type="PREMIUM").count(), 1)
        self.assertEqual(UsdLedgerEntry.objects.filter(wallet__user=user, kind="PREMIUM_PURCHASE").count(), 1)
