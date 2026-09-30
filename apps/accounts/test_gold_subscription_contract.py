from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
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
        self.assertEqual(first.data["wallet"], {"balance_usd": "0.00", "display_currency": "USD"})
        self.assertEqual(first.data["user"]["access_level"], 5)
        self.assertFalse(first.data["subscription"]["can_start_trial"])
        self.assertFalse(first.data["subscription"]["can_request"])
        wallet = Wallet.objects.get(user=self.user)
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance_usd, 0)
        self.assertFalse(UsdLedgerEntry.objects.filter(wallet=wallet).exists())
        self.assertFalse(UpgradeRequest.objects.filter(user=self.user).exists())

        second = self.client.post(
            "/api/accounts/upgrade-requests/premium/trial/activate/", {}, format="json"
        )
        self.user.refresh_from_db()
        self.assertEqual(second.status_code, 200)
        self.assertEqual(self.user.gold_trial_started_at, started_at)
        self.assertEqual(self.user.gold_trial_expires_at, expires_at)

    def test_free_trial_works_with_existing_zero_balance_and_never_creates_debit(self):
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

    def test_trial_is_available_once_for_every_access_level(self):
        for level in User.AccessLevel.values:
            with self.subTest(access_level=level):
                User.objects.filter(pk=self.user.pk).update(
                    access_level=level,
                    gold_trial_started_at=None,
                    gold_trial_expires_at=None,
                    gold_permanent_granted_at=None,
                )
                self.user.refresh_from_db()
                response = self.client.post(
                    "/api/accounts/upgrade-requests/premium/trial/activate/",
                    {},
                    format="json",
                )
                self.assertEqual(response.status_code, 200)
                self.user.refresh_from_db()
                self.assertEqual(self.user.access_level, User.AccessLevel.LEVEL_5)
                self.assertEqual(
                    self.user.gold_trial_expires_at - self.user.gold_trial_started_at,
                    timedelta(days=7),
                )

    def test_trial_does_not_require_market_type(self):
        User.objects.filter(pk=self.user.pk).update(market_type="")
        response = self.client.post(
            "/api/accounts/upgrade-requests/premium/trial/activate/", {}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.access_level, User.AccessLevel.LEVEL_5)

    def test_used_trial_returns_exact_conflict_and_does_not_extend(self):
        started = timezone.now() - timedelta(days=8)
        expires = started + timedelta(days=7)
        User.objects.filter(pk=self.user.pk).update(
            access_level=User.AccessLevel.LEVEL_2,
            gold_trial_started_at=started,
            gold_trial_expires_at=expires,
        )
        response = self.client.post(
            "/api/accounts/upgrade-requests/premium/trial/activate/", {}, format="json"
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.data,
            {"code": "TRIAL_ALREADY_USED", "detail": "اشتراک آزمایشی قبلاً استفاده شده است."},
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.gold_trial_started_at, started)
        self.assertEqual(self.user.gold_trial_expires_at, expires)

    def test_trial_requires_authentication(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(
            "/api/accounts/upgrade-requests/premium/trial/activate/", {}, format="json"
        )
        self.assertEqual(response.status_code, 401)

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

    def test_dashboard_and_profile_details_refresh_expired_trial_from_bearer_request(self):
        from rest_framework_simplejwt.tokens import RefreshToken

        now = timezone.now()
        User.objects.filter(pk=self.user.pk).update(
            access_level=User.AccessLevel.LEVEL_5,
            gold_trial_started_at=now - timedelta(days=8),
            gold_trial_expires_at=now - timedelta(seconds=1),
        )
        self.client.force_authenticate(user=None)
        token = str(RefreshToken.for_user(self.user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        dashboard_response = self.client.get("/api/dashboard/")
        details_response = self.client.get("/api/accounts/profile/details/")
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertEqual(details_response.status_code, 200)
        dashboard = dashboard_response.data["data"]
        dashboard_subscription = dashboard["premium_subscription"]
        self.assertEqual(dashboard["access_level"], 2)
        self.assertEqual(dashboard["user"]["access_level"], 2)
        self.assertEqual(dashboard_subscription["status"], "EXPIRED")
        self.assertTrue(dashboard_subscription["can_request"])
        self.assertEqual(details_response.data["access_level"], 2)
        self.assertEqual(details_response.data["premium_subscription"]["status"], "EXPIRED")
        self.assertTrue(details_response.data["premium_subscription"]["can_request"])
        wallet_response = self.client.get("/api/wallet/")
        self.assertEqual(wallet_response.status_code, 200)
        self.assertEqual(wallet_response.data["balance_usd"], "0.00")

    def test_permanent_request_is_rejected_for_level_two_without_expired_trial(self):
        self.user.access_level = User.AccessLevel.LEVEL_2
        self.user.save(update_fields=("access_level", "updated_at"))
        response = self.client.post(
            "/api/accounts/upgrade-requests/premium/request/", {"message": ""}, format="json"
        )
        self.assertEqual(response.status_code, 400)

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
        self.user.gold_trial_started_at = timezone.now() - timedelta(days=8)
        self.user.gold_trial_expires_at = timezone.now() - timedelta(days=1)
        self.user.save(update_fields=(
            "access_level", "market_type", "gold_trial_started_at",
            "gold_trial_expires_at", "updated_at"
        ))
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
        self.assertIsNone(response.data["subscription"]["trial_expires_at"])
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


class GoldTrialConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def test_concurrent_trial_activation_keeps_one_seven_day_window(self):
        if connection.vendor == "sqlite":
            self.skipTest("Row-lock concurrency is verified on PostgreSQL, not SQLite.")
        user = User.objects.create_user(
            username="concurrent-trial-user",
            password="pass",
            market_type=User.MarketType.CRYPTO,
        )

        def activate():
            close_old_connections()
            try:
                candidate = User.objects.get(pk=user.pk)
                result = PremiumAccessService.activate_trial(candidate)
                return result.gold_trial_started_at, result.gold_trial_expires_at
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: activate(), range(2)))

        user.refresh_from_db()
        self.assertEqual(results[0], results[1])
        self.assertEqual(user.gold_trial_expires_at - user.gold_trial_started_at, timedelta(days=7))
        self.assertEqual(user.access_level, User.AccessLevel.LEVEL_5)
        self.assertEqual(User.objects.filter(pk=user.pk, gold_trial_started_at__isnull=False).count(), 1)
