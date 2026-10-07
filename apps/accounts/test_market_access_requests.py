from unittest.mock import patch

from django.test import override_settings
from rest_framework.test import APITestCase

from .market_access import resolve_market_access
from .market_access_requests import review_market_access_request
from .models import MarketAccessRequest, TrialGrant, UpgradeRequest, User, UserAccessAudit, UserMarketGrant
from apps.wallet.services import WalletService


@override_settings(MARKET_ACCESS_V2_ENABLED=True, CRM_ENABLED=False)
class MarketAccessRequestAPITests(APITestCase):
    my_url = "/api/accounts/market-access/requests/"
    admin_url = "/api/accounts/admin/market-access/requests/"
    preferences_url = "/api/accounts/profile/market-preferences/"

    def setUp(self):
        self.admin = User.objects.create_user(username="request-admin", role=User.Role.SUPER_ADMIN)
        self.support = User.objects.create_user(username="request-support", role=User.Role.SUPPORT)
        self.user = User.objects.create_user(
            username="request-user", first_name="Test", last_name="Trader", phone="09121112233"
        )
        self.other = User.objects.create_user(username="request-other")
        self.client.force_authenticate(self.user)

    def select(self, markets):
        response = self.client.put(
            self.preferences_url, {"selected_markets": markets}, format="json"
        )
        self.assertEqual(response.status_code, 200)

    def submit(self, tier="PRO"):
        return self.client.post(self.my_url, {"requested_tier": tier}, format="json")

    def review(self, application, data):
        self.client.force_authenticate(self.admin)
        return self.client.patch(
            f"{self.admin_url}{application.pk}/review/", data, format="json"
        )

    def test_selected_markets_required_and_tier_options_are_consistent(self):
        self.assertEqual(self.submit().status_code, 400)
        self.select(["crypto"])
        self.assertEqual(self.submit("PRO").status_code, 400)
        self.assertEqual(self.submit("GOLD").status_code, 400)
        self.assertEqual(self.submit("ELITE").status_code, 201)

    def test_submit_is_idempotent_and_does_not_change_access_or_wallet(self):
        self.select(["crypto", "forex"])
        before_subscription = WalletService.premium_subscription(self.user)
        self.assertFalse(before_subscription["can_start_trial"])
        self.assertTrue(before_subscription["can_request"])
        first = self.submit()
        second = self.submit()
        self.assertEqual((first.status_code, second.status_code), (201, 200))
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(first.data["requested_markets"], ["crypto", "forex"])
        self.assertEqual(MarketAccessRequest.objects.filter(user=self.user).count(), 1)
        self.assertEqual(resolve_market_access(self.user).membership_tier, "LEVEL_1")
        self.assertFalse(UserMarketGrant.objects.filter(user=self.user).exists())
        self.assertFalse(UpgradeRequest.objects.filter(user=self.user).exists())
        self.assertFalse(TrialGrant.objects.filter(user=self.user).exists())
        self.assertFalse(WalletService.premium_subscription(self.user)["can_request"])
        self.assertEqual(self.submit("ELITE").status_code, 409)

    def test_manager_sees_contact_and_checkboxes_then_approves_derived_pro(self):
        self.select(["internal", "crypto", "forex"])
        application = MarketAccessRequest.objects.get(pk=self.submit("GOLD").data["id"])
        self.client.force_authenticate(self.support)
        listing = self.client.get(self.admin_url, {"status": "PENDING", "search": "09121112233"})
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["count"], 1)
        item = listing.data["results"][0]
        self.assertEqual(item["requested_markets"], ["crypto", "forex", "internal"])
        self.assertEqual(item["user"]["phone"], self.user.phone)
        self.assertTrue(item["tier_description"])

        approved = self.client.patch(
            f"{self.admin_url}{application.pk}/review/",
            {"status": "APPROVED", "approved_markets": ["crypto", "forex"], "admin_note": "Two markets approved."},
            format="json",
        )
        self.assertEqual(approved.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.access_level, 1)
        self.assertEqual(resolve_market_access(self.user).membership_tier, "PRO")
        self.assertEqual(
            set(UserMarketGrant.objects.filter(user=self.user).values_list("source", flat=True)),
            {UserMarketGrant.Source.APPROVED_REQUEST},
        )
        application.refresh_from_db()
        self.assertEqual(application.approved_markets, ["crypto", "forex"])
        self.assertEqual(application.reviewed_by_id, self.support.pk)
        self.assertEqual(
            UserAccessAudit.objects.filter(subject_user_id=self.user.pk, action=UserAccessAudit.Action.MARKET_GRANTED).count(),
            2,
        )
        self.assertEqual(
            self.client.patch(f"{self.admin_url}{application.pk}/review/", {"status": "APPROVED", "approved_markets": ["crypto", "forex"]}, format="json").status_code,
            409,
        )

    def test_gold_and_elite_are_independent_of_legacy_level(self):
        self.select(["crypto", "forex", "internal"])
        application = MarketAccessRequest.objects.get(pk=self.submit("ELITE").data["id"])
        self.assertEqual(self.review(application, {
            "status": "APPROVED", "approved_markets": ["crypto"], "is_elite": True,
        }).status_code, 200)
        self.user.refresh_from_db()
        state = resolve_market_access(self.user)
        self.assertEqual(state.membership_tier, "BASIC")
        self.assertTrue(state.is_elite)
        self.assertEqual(self.user.access_level, 1)

        self.client.force_authenticate(self.user)
        gold = MarketAccessRequest.objects.get(pk=self.submit("GOLD").data["id"])
        self.assertEqual(self.review(gold, {
            "status": "APPROVED", "approved_markets": ["crypto", "forex", "internal"],
        }).status_code, 200)
        self.user.refresh_from_db()
        state = resolve_market_access(self.user)
        self.assertEqual(state.membership_tier, "GOLD")
        self.assertTrue(state.is_elite)
        v2_subscription = WalletService.premium_subscription(self.user)
        self.assertTrue(v2_subscription["active"])
        self.assertEqual(v2_subscription["tier"], "GOLD")
        self.assertIsNone(v2_subscription["access_level"])
        self.assertIsNone(v2_subscription["plan_id"])
        self.assertFalse(v2_subscription["can_start_trial"])

    def test_rejection_preserves_access_and_records_reviewer(self):
        self.select(["crypto", "forex"])
        application = MarketAccessRequest.objects.get(pk=self.submit().data["id"])
        response = self.review(application, {"status": "REJECTED", "admin_note": "Needs review."})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(resolve_market_access(self.user).membership_tier, "LEVEL_1")
        application.refresh_from_db()
        self.assertEqual(application.status, "REJECTED")
        self.assertEqual(application.admin_note, "Needs review.")
        self.assertFalse(UserMarketGrant.objects.filter(user=self.user).exists())

    def test_changed_preferences_or_unselected_market_blocks_approval(self):
        self.select(["crypto", "forex"])
        application = MarketAccessRequest.objects.get(pk=self.submit().data["id"])
        self.assertEqual(self.review(application, {
            "status": "APPROVED", "approved_markets": ["internal"],
        }).status_code, 400)
        self.client.force_authenticate(self.user)
        self.select(["crypto"])
        self.assertEqual(self.review(application, {
            "status": "APPROVED", "approved_markets": ["crypto"],
        }).status_code, 409)
        application.refresh_from_db()
        self.assertEqual(application.status, "PENDING")
        self.assertFalse(UserMarketGrant.objects.filter(user=self.user).exists())

    def test_permissions_and_isolation(self):
        self.select(["crypto", "forex"])
        application = MarketAccessRequest.objects.get(pk=self.submit().data["id"])
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(self.my_url).data["count"], 0)
        self.assertEqual(self.client.get(self.admin_url).status_code, 403)
        self.assertEqual(self.client.patch(
            f"{self.admin_url}{application.pk}/review/",
            {"status": "REJECTED"}, format="json",
        ).status_code, 403)
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(self.my_url).status_code, 401)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.submit("ELITE").status_code, 403)
        with override_settings(MARKET_ACCESS_V2_ENABLED=False):
            self.assertEqual(self.client.get(self.admin_url).status_code, 403)
            self.assertEqual(self.client.get(self.my_url).status_code, 403)

    def test_audit_failure_rolls_back_review_and_grants(self):
        self.select(["crypto", "forex"])
        application = MarketAccessRequest.objects.get(pk=self.submit().data["id"])
        with patch.object(UserAccessAudit.objects, "create", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                review_market_access_request(
                    actor=self.admin, request_id=application.pk,
                    status="APPROVED", approved_markets=["crypto", "forex"],
                )
        application.refresh_from_db()
        self.assertEqual(application.status, "PENDING")
        self.assertFalse(UserMarketGrant.objects.filter(user=self.user).exists())
