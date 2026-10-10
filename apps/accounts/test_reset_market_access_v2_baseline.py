import json
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.market_access import resolve_market_access
from apps.accounts.market_access_requests import (
    MarketAccessRequestConflict,
    review_market_access_request,
    submit_market_access_request,
)
from apps.accounts.market_preferences import update_market_preferences
from apps.accounts.market_trial import eligible_trial_users
from apps.accounts.models import (
    MarketAccessRequest,
    TrialCampaign,
    TrialGrant,
    UpgradeRequest,
    User,
    UserAccessAudit,
    UserAccessProfile,
    UserMarketGrant,
    UserMarketPreference,
)


@override_settings(MARKET_ACCESS_V2_ENABLED=True, CRM_ENABLED=False)
class ResetMarketAccessV2BaselineTests(TestCase):
    def setUp(self):
        self.superadmin = User.objects.create_superuser(
            username="reset-superadmin", email="reset-admin@example.com", password="SafePass123!",
            access_level=5,
        )
        self.support = User.objects.create_user(
            username="reset-support", role=User.Role.SUPPORT, access_level=5
        )
        self.user = User.objects.create_user(
            username="reset-user", role=User.Role.ADMIN, access_level=5,
            gold_trial_started_at=timezone.now(),
            gold_trial_expires_at=timezone.now() + timedelta(days=7),
        )
        self.untried = User.objects.create_user(
            username="reset-untried", access_level=3,
            gold_trial_started_at=timezone.now() - timedelta(days=8),
            gold_trial_expires_at=timezone.now() - timedelta(days=1),
        )
        UserMarketPreference.objects.create(user=self.user, market="crypto")
        UserAccessProfile.objects.create(
            user=self.user, market_selection_confirmed_at=timezone.now(), is_elite=True
        )
        UserMarketGrant.objects.create(
            user=self.user, market="crypto", source=UserMarketGrant.Source.ADMIN
        )
        self.campaign = TrialCampaign.objects.create(created_by=self.superadmin)
        TrialGrant.objects.create(
            user=self.user, campaign=self.campaign,
            started_at=timezone.now(), ends_at=timezone.now() + timedelta(days=7),
        )
        UserMarketGrant.objects.create(
            user=self.support, market="forex", source=UserMarketGrant.Source.ADMIN
        )

    def _run(self, **options):
        output = StringIO()
        call_command("reset_market_access_v2_baseline", stdout=output, **options)
        return json.loads(output.getvalue())

    def test_preview_is_read_only_and_apply_requires_explicit_trial_confirmation(self):
        preview = self._run()
        self.assertEqual(preview["mode"], "dry_run")
        self.assertEqual(preview["legacy_levels_to_one"], 2)
        self.assertEqual(preview["market_confirmations_to_reset"], 1)
        self.assertEqual(preview["active_or_scheduled_v2_trials_to_revoke"], 1)
        self.assertEqual(preview["v2_trial_history_retained"], 1)
        self.assertEqual(preview["eligible_for_future_v2_trial_after_reset"], 1)
        self.assertEqual(preview["legacy_trial_history_ignored"], 2)
        self.assertFalse(UserAccessAudit.objects.exists())
        self.assertEqual(User.objects.get(pk=self.user.pk).access_level, 5)
        with self.assertRaises(CommandError):
            self._run(apply=True)

    def test_apply_resets_normal_users_and_market_prompt_without_reusing_trial(self):
        applied = self._run(apply=True, confirm_trials_remain_used=True)
        self.assertEqual(applied["mode"], "apply")
        self.assertEqual(applied["users_to_audit"], 2)
        self.user.refresh_from_db()
        self.untried.refresh_from_db()
        self.support.refresh_from_db()
        self.superadmin.refresh_from_db()
        self.assertEqual(self.user.access_level, 1)
        self.assertEqual(self.untried.access_level, 1)
        self.assertEqual(self.support.access_level, 5)
        self.assertEqual(self.superadmin.access_level, 5)
        self.assertFalse(self.user.has_gold_access)
        self.assertIsNotNone(self.user.gold_trial_started_at)  # Historical data is retained.
        self.assertIsNone(UserAccessProfile.objects.get(user=self.user).market_selection_confirmed_at)
        self.assertFalse(UserAccessProfile.objects.get(user=self.user).is_elite)
        self.assertEqual(list(UserMarketPreference.objects.filter(user=self.user).values_list("market", flat=True)), ["crypto"])
        self.assertIsNotNone(TrialGrant.objects.get(user=self.user).revoked_at)
        self.assertIsNotNone(UserMarketGrant.objects.get(user=self.user).revoked_at)
        self.assertIsNone(UserMarketGrant.objects.get(user=self.support).revoked_at)
        state = resolve_market_access(self.user)
        self.assertEqual(state.membership_tier, "LEVEL_1")
        self.assertFalse(state.market_selection_confirmed)
        self.assertFalse(state.trial_active)
        self.assertFalse(state.effective_markets)
        self.assertFalse(eligible_trial_users().filter(pk=self.user.pk).exists())
        self.assertTrue(eligible_trial_users().filter(pk=self.untried.pk).exists())
        self.assertEqual(UserAccessAudit.objects.filter(action=UserAccessAudit.Action.LEGACY_RESET).count(), 2)
        client = APIClient()
        client.force_authenticate(self.user)
        preferences = client.get("/api/accounts/profile/market-preferences/")
        self.assertEqual(preferences.status_code, 200)
        self.assertEqual(preferences.data["membership_tier"], "LEVEL_1")
        self.assertFalse(preferences.data["market_selection_confirmed"])
        profile = client.get("/api/accounts/profile/")
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.data["access_level"], 1)
        self.assertFalse(profile.data["market_access_v2"]["market_selection_confirmed"])
        repeated = self._run(apply=True, confirm_trials_remain_used=True)
        self.assertEqual(repeated["users_to_audit"], 0)
        self.assertEqual(UserAccessAudit.objects.filter(action=UserAccessAudit.Action.LEGACY_RESET).count(), 2)

    def test_approved_legacy_request_save_cannot_regrant_level_five(self):
        self._run(apply=True, confirm_trials_remain_used=True)
        request = UpgradeRequest.objects.create(
            user=self.user, request_type=UpgradeRequest.Type.PREMIUM,
            requested_level=5, status=UpgradeRequest.Status.APPROVED,
        )
        request.save(update_fields=("status",))
        self.user.refresh_from_db()
        self.assertEqual(self.user.access_level, 1)

    def test_old_pending_request_needs_fresh_selection_and_application(self):
        old_request = MarketAccessRequest.objects.create(
            user=self.user,
            requested_tier=MarketAccessRequest.RequestedTier.ELITE,
            requested_markets=["crypto"],
        )
        self._run(apply=True, confirm_trials_remain_used=True)
        with self.assertRaises(MarketAccessRequestConflict):
            review_market_access_request(
                actor=self.superadmin, request_id=old_request.pk,
                status=MarketAccessRequest.Status.APPROVED, approved_markets=["crypto"],
            )
        update_market_preferences(user=self.user, selected_markets=["crypto"])
        new_request, created = submit_market_access_request(
            user=self.user, requested_tier=MarketAccessRequest.RequestedTier.ELITE
        )
        self.assertTrue(created)
        self.assertNotEqual(new_request.pk, old_request.pk)
        old_request.refresh_from_db()
        self.assertEqual(old_request.status, MarketAccessRequest.Status.REJECTED)

    def test_audit_failure_rolls_back_every_reset_change(self):
        with patch.object(UserAccessAudit.objects, "bulk_create", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                self._run(apply=True, confirm_trials_remain_used=True)
        self.user.refresh_from_db()
        self.assertEqual(self.user.access_level, 5)
        self.assertIsNone(UserMarketGrant.objects.get(user=self.user).revoked_at)
        self.assertIsNone(TrialGrant.objects.get(user=self.user).revoked_at)
        self.assertIsNotNone(UserAccessProfile.objects.get(user=self.user).market_selection_confirmed_at)


class ResetMarketAccessV2BaselineGateTests(TestCase):
    @override_settings(MARKET_ACCESS_V2_ENABLED=False)
    def test_apply_rejects_disabled_v2(self):
        with self.assertRaises(CommandError):
            call_command(
                "reset_market_access_v2_baseline",
                apply=True,
                confirm_trials_remain_used=True,
                stdout=StringIO(),
            )
