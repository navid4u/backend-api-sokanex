from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase
from unittest.mock import patch

from apps.accounts.models import UpgradeRequest, User
from apps.accounts.services import PremiumAccessService
from apps.accounts.views import RegisterView
from apps.wallet.models import UsdLedgerEntry, Wallet


class GoldSubscriptionContractTests(APITestCase):
    password = "StrongPassword!123"

    def setUp(self):
        self.user = User.objects.create_user(
            username="gold-contract-user",
            phone="09121234567",
            password=self.password,
            market_type=User.MarketType.CRYPTO,
        )
        self.client.force_authenticate(self.user)

    def test_trial_is_exactly_seven_days_and_repeat_is_idempotent(self):
        wallet = Wallet.objects.create(user=self.user, balance_usd="100.00")
        ledger_before = UsdLedgerEntry.objects.filter(wallet=wallet).count()
        first = self.client.post(
            "/api/accounts/upgrade-requests/premium/trial/activate/", {}, format="json"
        )
        self.assertEqual(first.status_code, 200)
        self.user.refresh_from_db()
        started_at = self.user.gold_trial_started_at
        expires_at = self.user.gold_trial_expires_at
        self.assertEqual(expires_at - started_at, timedelta(days=7))
        self.assertEqual(first.data["subscription"]["status"], "ACTIVE")
        self.assertTrue(first.data["subscription"]["trial"])
        self.assertEqual(first.data["subscription"]["days_remaining"], 7)
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance_usd, 100)
        self.assertEqual(UsdLedgerEntry.objects.filter(wallet=wallet).count(), ledger_before)

        second = self.client.post(
            "/api/accounts/upgrade-requests/premium/trial/activate/", {}, format="json"
        )
        self.user.refresh_from_db()
        self.assertEqual(second.status_code, 200)
        self.assertEqual(self.user.gold_trial_started_at, started_at)
        self.assertEqual(self.user.gold_trial_expires_at, expires_at)

    def test_free_trial_works_with_zero_balance_and_never_creates_debit(self):
        wallet = Wallet.objects.create(user=self.user, balance_usd="0.00")
        response = self.client.post(
            "/api/accounts/upgrade-requests/premium/trial/activate/", {}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance_usd, 0)
        self.assertFalse(
            UsdLedgerEntry.objects.filter(wallet=wallet, direction=UsdLedgerEntry.Direction.DEBIT).exists()
        )

    def test_expired_trial_downgrades_to_level_two_and_can_request(self):
        now = timezone.now()
        User.objects.filter(pk=self.user.pk).update(
            access_level=User.AccessLevel.LEVEL_5,
            gold_trial_started_at=now - timedelta(days=8),
            gold_trial_expires_at=now - timedelta(days=1),
        )
        updated = PremiumAccessService.expire_trials()
        self.assertEqual(updated, 1)
        self.user.refresh_from_db()
        self.assertEqual(self.user.access_level, User.AccessLevel.LEVEL_2)
        self.client.force_authenticate(self.user)
        profile = self.client.get("/api/accounts/profile/")
        subscription = profile.data["premium_subscription"]
        self.assertFalse(subscription["active"])
        self.assertTrue(subscription["trial"])
        self.assertEqual(subscription["status"], "EXPIRED")
        self.assertEqual(subscription["days_remaining"], 0)
        self.assertFalse(subscription["can_start_trial"])
        self.assertTrue(subscription["can_request"])

    def test_permanent_request_is_idempotent_and_targets_level_three(self):
        self.user.access_level = User.AccessLevel.LEVEL_2
        self.user.gold_trial_started_at = timezone.now() - timedelta(days=8)
        self.user.gold_trial_expires_at = timezone.now() - timedelta(days=1)
        self.user.save(update_fields=(
            "access_level", "gold_trial_started_at", "gold_trial_expires_at", "updated_at"
        ))
        self.client.force_authenticate(self.user)
        url = "/api/accounts/upgrade-requests/premium/request/"
        first = self.client.post(url, {"message": "Please review."}, format="json")
        second = self.client.post(url, {"message": "Repeat click."}, format="json")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data["upgrade_request"]["requested_level"], 3)
        self.assertEqual(
            first.data["upgrade_request"]["id"],
            second.data["upgrade_request"]["id"],
        )
        self.assertEqual(
            UpgradeRequest.objects.filter(
                user=self.user,
                request_type=UpgradeRequest.Type.PREMIUM,
                status=UpgradeRequest.Status.PENDING,
            ).count(),
            1,
        )

    def test_admin_approval_grants_permanent_gold_at_level_three(self):
        self.user.access_level = User.AccessLevel.LEVEL_2
        self.user.market_type = User.MarketType.FOREX
        self.user.save(update_fields=("access_level", "market_type", "updated_at"))
        request = UpgradeRequest.objects.create(
            user=self.user,
            request_type=UpgradeRequest.Type.PREMIUM,
            requested_level=User.AccessLevel.LEVEL_3,
            grant_source=UpgradeRequest.GrantSource.GOLD_RENEWAL_REQUEST,
        )
        admin = User.objects.create_user(
            username="gold-contract-admin",
            password=self.password,
            role=User.Role.SUPER_ADMIN,
        )
        self.client.force_authenticate(admin)
        response = self.client.patch(
            f"/api/accounts/admin/upgrade-requests/{request.pk}/review/",
            {"status": "APPROVED", "admin_note": "Approved"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.access_level, User.AccessLevel.LEVEL_3)
        self.assertIsNotNone(self.user.gold_permanent_granted_at)
        self.assertTrue(response.data["subscription"]["active"])
        self.assertFalse(response.data["subscription"]["trial"])
        self.assertEqual(response.data["subscription"]["status"], "ACTIVE")

    @patch.object(RegisterView, "throttle_classes", [])
    def test_username_registration_returns_hashed_password_and_tokens(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(
            "/api/accounts/register/",
            {
                "first_name": "Ali",
                "last_name": "Ahmadi",
                "phone": "09351234567",
                "username": "sokanex.user",
                "password": "AnotherStrong123!",
                "password_confirm": "AnotherStrong123!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        created = User.objects.get(username="sokanex.user")
        self.assertTrue(created.check_password("AnotherStrong123!"))
        self.assertNotEqual(created.password, "AnotherStrong123!")
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertIn("premium_subscription", response.data["user"])
        self.assertTrue(response.data["user"]["premium_subscription"]["can_start_trial"])

    @patch.object(RegisterView, "throttle_classes", [])
    def test_duplicate_username_password_mismatch_and_invalid_phone_are_400(self):
        self.client.force_authenticate(user=None)
        base = {
            "first_name": "Ali",
            "last_name": "Ahmadi",
            "phone": "09351234567",
            "username": "sokanex.user",
            "password": "AnotherStrong123!",
            "password_confirm": "AnotherStrong123!",
        }
        self.assertEqual(self.client.post("/api/accounts/register/", base, format="json").status_code, 201)
        duplicate = {**base, "phone": "09351234568"}
        duplicate_response = self.client.post("/api/accounts/register/", duplicate, format="json")
        self.assertEqual(duplicate_response.status_code, 400)
        self.assertIn("username", duplicate_response.data["errors"])
        mismatch = {**base, "phone": "09351234569", "username": "another.user", "password_confirm": "wrong"}
        mismatch_response = self.client.post("/api/accounts/register/", mismatch, format="json")
        self.assertEqual(mismatch_response.status_code, 400)
        invalid_phone = {**base, "phone": "not-a-phone", "username": "third.user"}
        invalid_response = self.client.post("/api/accounts/register/", invalid_phone, format="json")
        self.assertEqual(invalid_response.status_code, 400)
