from datetime import date, timedelta
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from .market_access import MARKETS, resolve_market_access
from .market_trial import eligible_trial_users, start_trial_campaign, trial_candidate_digest
from .models import TrialCampaign, TrialGrant, User, UserAccessAudit, UserMarketGrant
from .services import LegacyGoldFlowDisabled, PremiumAccessService


@override_settings(MARKET_ACCESS_V2_ENABLED=True, CRM_ENABLED=False)
class MarketTrialCampaignTests(APITestCase):
    preview_url = "/api/accounts/admin/market-access/trial-campaigns/preview/"
    start_url = "/api/accounts/admin/market-access/trial-campaigns/"

    def setUp(self):
        self.admin = User.objects.create_user(username="trial-v2-admin", role=User.Role.SUPER_ADMIN)
        self.support = User.objects.create_user(username="trial-v2-support", role=User.Role.SUPPORT)
        self.user = User.objects.create_user(username="trial-v2-user")
        self.client.force_authenticate(self.admin)

    def preview(self, **data):
        return self.client.post(self.preview_url, data, format="json")

    def start(self, expected_count, **data):
        registered_from = data.get("registered_from")
        if isinstance(registered_from, str):
            registered_from = date.fromisoformat(registered_from)
        cohort_ids = list(
            eligible_trial_users(registered_from=registered_from)
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        return self.client.post(
            self.start_url,
            {
                "confirm": True,
                "expected_eligible_count": expected_count,
                "expected_candidate_digest": trial_candidate_digest(cohort_ids),
                **data,
            },
            format="json",
        )

    def test_preview_is_read_only_and_excludes_special_inactive_granted_and_used(self):
        User.objects.create_user(username="trial-v2-inactive", is_active=False)
        granted = User.objects.create_user(username="trial-v2-granted")
        UserMarketGrant.objects.create(
            user=granted, market=User.MarketType.CRYPTO,
            source=UserMarketGrant.Source.ADMIN, granted_by=self.admin,
        )
        used = User.objects.create_user(username="trial-v2-used")
        old_campaign = TrialCampaign.objects.create(created_by=self.admin)
        now = timezone.now()
        TrialGrant.objects.create(
            user=used, campaign=old_campaign,
            started_at=now - timedelta(days=8), ends_at=now - timedelta(days=1),
        )
        response = self.preview()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["eligible_count"], 1)
        self.assertEqual(response.data["duration_days"], 7)
        self.assertEqual(TrialGrant.objects.count(), 1)
        self.assertFalse(UserAccessAudit.objects.exists())

    def test_superadmin_starts_exact_seven_day_trial_once_without_touching_legacy(self):
        old_started = timezone.now() - timedelta(days=30)
        old_ends = old_started + timedelta(days=7)
        User.objects.filter(pk=self.user.pk).update(
            access_level=User.AccessLevel.LEVEL_5,
            gold_trial_started_at=old_started,
            gold_trial_expires_at=old_ends,
        )
        self.assertEqual(self.preview().data["eligible_count"], 1)
        response = self.start(1)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], TrialCampaign.Status.APPLIED)
        self.assertEqual(response.data["granted_count"], 1)
        grant = TrialGrant.objects.get(user=self.user)
        self.assertEqual(grant.ends_at - grant.started_at, timedelta(days=7))
        self.assertEqual(grant.campaign_id, response.data["id"])
        self.assertEqual(
            UserAccessAudit.objects.filter(
                subject_user_id=self.user.pk, action=UserAccessAudit.Action.TRIAL_STARTED
            ).count(),
            1,
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.access_level, User.AccessLevel.LEVEL_5)
        self.assertEqual(self.user.gold_trial_started_at, old_started)
        self.assertEqual(self.user.gold_trial_expires_at, old_ends)
        state = resolve_market_access(self.user, at=grant.started_at + timedelta(seconds=1))
        self.assertEqual(state.membership_tier, "LEVEL_1")
        self.assertTrue(state.trial_active)
        self.assertEqual(state.effective_markets, MARKETS)
        expired = resolve_market_access(self.user, at=grant.ends_at)
        self.assertFalse(expired.trial_active)
        self.assertFalse(expired.effective_markets)

    def test_repeat_never_extends_trial_or_creates_second_grant(self):
        self.assertEqual(self.start(1).status_code, 201)
        first = TrialGrant.objects.get(user=self.user)
        response = self.start(1)
        self.assertEqual(response.status_code, 409)
        first.refresh_from_db()
        self.assertEqual(TrialGrant.objects.filter(user=self.user).count(), 1)
        self.assertEqual(TrialCampaign.objects.count(), 1)
        self.assertEqual(self.preview().data["eligible_count"], 0)

    def test_stale_preview_or_missing_confirmation_writes_nothing(self):
        self.assertEqual(self.start(2).status_code, 409)
        self.assertEqual(
            self.client.post(
                self.start_url,
                {"confirm": False, "expected_eligible_count": 1},
                format="json",
            ).status_code,
            400,
        )
        self.assertFalse(TrialCampaign.objects.exists())
        self.assertFalse(TrialGrant.objects.exists())

    def test_same_count_but_changed_cohort_is_rejected(self):
        original = self.preview().data
        replacement = User.objects.create_user(username="trial-v2-replacement")
        UserMarketGrant.objects.create(
            user=self.user, market=User.MarketType.FOREX,
            source=UserMarketGrant.Source.ADMIN, granted_by=self.admin,
        )
        response = self.client.post(
            self.start_url,
            {
                "confirm": True,
                "expected_eligible_count": original["eligible_count"],
                "expected_candidate_digest": original["candidate_digest"],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertFalse(TrialGrant.objects.filter(user=replacement).exists())
        self.assertFalse(TrialCampaign.objects.exists())

    def test_registered_from_limits_candidates(self):
        older = User.objects.create_user(username="trial-v2-older")
        User.objects.filter(pk=older.pk).update(date_joined=timezone.now() - timedelta(days=30))
        since = timezone.localdate() - timedelta(days=1)
        response = self.preview(registered_from=since.isoformat())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["eligible_count"], 1)
        applied = self.start(1, registered_from=since.isoformat())
        self.assertEqual(applied.status_code, 201)
        self.assertTrue(TrialGrant.objects.filter(user=self.user).exists())
        self.assertFalse(TrialGrant.objects.filter(user=older).exists())

    def test_only_superadmin_can_preview_or_start_and_flag_must_be_on(self):
        self.client.force_authenticate(self.support)
        self.assertEqual(self.preview().status_code, 403)
        self.assertEqual(self.start(1).status_code, 403)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.start(1).status_code, 403)
        self.client.force_authenticate(self.admin)
        with override_settings(MARKET_ACCESS_V2_ENABLED=False):
            self.assertEqual(self.preview().status_code, 403)
            self.assertEqual(self.start(1).status_code, 403)
        self.assertFalse(TrialGrant.objects.exists())

    def test_invalid_date_or_unexpected_duration_is_rejected(self):
        self.assertEqual(self.preview(registered_from="1405/01/01").status_code, 400)
        self.assertEqual(self.start(1, duration_days=365).status_code, 400)
        self.assertFalse(TrialCampaign.objects.exists())

    def test_audit_failure_rolls_back_entire_campaign(self):
        digest = trial_candidate_digest([self.user.pk])
        with patch.object(UserAccessAudit.objects, "bulk_create", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                start_trial_campaign(
                    actor=self.admin,
                    expected_eligible_count=1,
                    expected_candidate_digest=digest,
                )
        self.assertFalse(TrialCampaign.objects.exists())
        self.assertFalse(TrialGrant.objects.exists())

    def test_v2_never_auto_starts_or_expires_legacy_trial(self):
        now = timezone.now()
        User.objects.filter(pk=self.user.pk).update(
            access_level=User.AccessLevel.LEVEL_5,
            gold_trial_started_at=None,
            gold_trial_expires_at=None,
        )
        self.user.refresh_from_db()
        PremiumAccessService.refresh_user_state(self.user)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.gold_trial_started_at)
        self.assertIsNone(self.user.gold_trial_expires_at)

        User.objects.filter(pk=self.user.pk).update(
            gold_trial_started_at=now - timedelta(days=8),
            gold_trial_expires_at=now - timedelta(days=1),
        )
        self.user.refresh_from_db()
        PremiumAccessService.refresh_user_state(self.user)
        self.assertEqual(PremiumAccessService.expire_trials(), 0)
        self.user.refresh_from_db()
        self.assertEqual(self.user.access_level, User.AccessLevel.LEVEL_5)

    def test_old_self_service_gold_routes_are_disabled_only_in_v2(self):
        self.client.force_authenticate(self.user)
        for url, payload in (
            ("/api/accounts/upgrade-requests/premium/trial/activate/", {}),
            ("/api/accounts/upgrade-requests/premium/request/", {"market_type": "CRYPTO"}),
            ("/api/accounts/upgrade-requests/premium/purchase/", {}),
            ("/api/accounts/upgrade-requests/", {}),
        ):
            with self.subTest(url=url):
                response = self.client.post(url, payload, format="json")
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.data["error_code"], "LEGACY_GOLD_FLOW_DISABLED")
        self.assertFalse(TrialGrant.objects.exists())
        self.user.refresh_from_db()
        self.assertIsNone(self.user.gold_trial_started_at)

    def test_old_service_rejects_direct_trial_activation_in_v2(self):
        with self.assertRaises(LegacyGoldFlowDisabled):
            PremiumAccessService.activate_trial(self.user)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.gold_trial_started_at)

    def test_profile_and_dashboard_report_v2_trial_without_legacy_mutation(self):
        self.assertEqual(self.start(1).status_code, 201)
        self.client.force_authenticate(self.user)
        profile = self.client.get("/api/accounts/profile/")
        dashboard = self.client.get("/api/dashboard/")
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(dashboard.status_code, 200)
        self.assertTrue(profile.data["market_access_v2"]["trial_active"])
        self.assertTrue(profile.data["premium_subscription"]["active"])
        self.assertFalse(profile.data["premium_subscription"]["can_start_trial"])
        self.assertTrue(dashboard.data["data"]["market_access_v2"]["trial_active"])

        TrialGrant.objects.filter(user=self.user).update(
            started_at=timezone.now() - timedelta(days=8),
            ends_at=timezone.now() - timedelta(days=1),
        )
        self.client.force_authenticate(User.objects.get(pk=self.user.pk))
        expired_profile = self.client.get("/api/accounts/profile/")
        expired_dashboard = self.client.get("/api/dashboard/")
        self.assertFalse(expired_profile.data["market_access_v2"]["trial_active"])
        self.assertEqual(expired_profile.data["premium_subscription"]["status"], "EXPIRED")
        self.assertFalse(expired_dashboard.data["data"]["market_access_v2"]["trial_active"])
        self.user.refresh_from_db()
        self.assertEqual(self.user.access_level, User.AccessLevel.LEVEL_1)
