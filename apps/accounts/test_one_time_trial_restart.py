"""Exceptional, audited October 2026 seven-day restart contract."""

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.notifications.models import TrialJourneyActivation, TrialJourneyDay, TrialJourneyEnrollment

from .market_access import resolve_market_access
from .market_trial import (
    ONE_TIME_ALL_USERS_RESTART_KEY, TrialCampaignConflict,
    preview_all_users_trial_restart, restart_all_users_trial_once,
    start_new_user_trial, update_auto_start_settings,
)
from .models import (
    TrialCampaign, TrialGrant, User, UserAccessProfile, UserMarketGrant,
)


@override_settings(MARKET_ACCESS_V2_ENABLED=True, CRM_ENABLED=False)
class OneTimeTrialRestartTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="campaign-admin", role=User.Role.SUPER_ADMIN)
        self.support = User.objects.create_user(username="campaign-support", role=User.Role.SUPPORT)
        self.old_campaign = TrialCampaign.objects.create(created_by=self.admin, status=TrialCampaign.Status.APPLIED)
        update_auto_start_settings(actor=self.admin, auto_start_new_users=True)
        TrialJourneyActivation.objects.create(pk=1, activated_at=timezone.now() - timedelta(days=2))
        TrialJourneyDay.objects.update_or_create(
            day=1, defaults={"is_active": True, "text": "Welcome {first_name}"},
        )

    def _old_grant(self, user, *, active=False, invalidated=False):
        now = timezone.now()
        return TrialGrant.objects.create(
            user=user, campaign=self.old_campaign,
            started_at=now - timedelta(days=1 if active else 9),
            ends_at=now + timedelta(days=6) if active else now - timedelta(days=2),
            invalidated_at=now if invalidated else None,
        )

    def _apply(self):
        preview = preview_all_users_trial_restart(actor=self.admin)
        return restart_all_users_trial_once(
            actor=self.admin,
            expected_eligible_count=preview["eligible_count"],
            expected_candidate_digest=preview["candidate_digest"],
        )

    def test_restart_preserves_active_and_special_but_restarts_used_users(self):
        active = User.objects.create_user(username="active-trial")
        active_grant = self._old_grant(active, active=True)
        used = User.objects.create_user(username="expired-trial", gold_trial_started_at=timezone.now() - timedelta(days=30))
        expired_grant = self._old_grant(used)
        invalidated = User.objects.create_user(username="invalidated-trial")
        old_invalidated = self._old_grant(invalidated, invalidated=True)
        inactive = User.objects.create_user(username="inactive-trial", is_active=False)
        fresh = User.objects.create_user(username="fresh-trial")
        granted = UserMarketGrant.objects.create(
            user=used, market=User.MarketType.FOREX,
            source=UserMarketGrant.Source.ADMIN, granted_by=self.admin,
        )
        UserAccessProfile.objects.create(user=used, is_elite=True)

        preview = preview_all_users_trial_restart(actor=self.admin)
        # A legacy data migration seeds one inactive ordinary account.
        self.assertEqual(preview["eligible_count"], preview["normal_users"] - 1)
        self.assertEqual(preview["active_trials_preserved"], 1)
        self.assertGreaterEqual(preview["inactive_eligible_users"], 1)
        self.assertEqual(preview["active_market_grants_to_revoke"], 1)
        result = self._apply()
        self.assertEqual(result["granted_count"], preview["eligible_count"])
        self.assertEqual(result["invalidated_old_grants"], 1)
        self.assertEqual(TrialCampaign.objects.get(operation_key=ONE_TIME_ALL_USERS_RESTART_KEY).status, "APPLIED")

        active_grant.refresh_from_db()
        self.assertIsNone(active_grant.invalidated_at)
        self.assertEqual(TrialGrant.objects.filter(user=active).count(), 1)
        expired_grant.refresh_from_db()
        self.assertIsNotNone(expired_grant.invalidated_at)
        old_invalidated.refresh_from_db()
        self.assertIsNotNone(old_invalidated.invalidated_at)
        self.assertEqual(TrialGrant.objects.filter(user=self.admin).count(), 0)
        self.assertEqual(TrialGrant.objects.filter(user=self.support).count(), 0)
        granted.refresh_from_db()
        self.assertIsNotNone(granted.revoked_at)
        self.assertFalse(UserAccessProfile.objects.get(user=used).is_elite)
        for user in (used, invalidated, inactive, fresh):
            current = TrialGrant.objects.get(user=user, invalidated_at__isnull=True)
            self.assertEqual(current.ends_at - current.started_at, timedelta(days=7))
            self.assertEqual(current.campaign_id, result["campaign_id"])
            self.assertTrue(TrialJourneyEnrollment.objects.filter(grant=current).exists())
        self.assertTrue(resolve_market_access(used).trial_active)
        self.assertFalse(resolve_market_access(used).granted_markets)

        again = self._apply()
        self.assertTrue(again["already_applied"])
        self.assertEqual(TrialGrant.objects.filter(user=used).count(), 2)

    def test_stale_preview_and_failed_write_leave_no_partial_changes(self):
        user = User.objects.create_user(username="stale-trial")
        preview = preview_all_users_trial_restart(actor=self.admin)
        User.objects.create_user(username="new-after-preview")
        with self.assertRaises(TrialCampaignConflict):
            restart_all_users_trial_once(
                actor=self.admin, expected_eligible_count=preview["eligible_count"],
                expected_candidate_digest=preview["candidate_digest"],
            )
        self.assertFalse(TrialCampaign.objects.filter(operation_key=ONE_TIME_ALL_USERS_RESTART_KEY).exists())
        self.assertFalse(TrialGrant.objects.filter(user=user).exists())

        with patch("apps.accounts.market_trial._create_trial_grants", side_effect=RuntimeError("test failure")):
            with self.assertRaises(RuntimeError):
                self._apply()
        self.assertFalse(TrialCampaign.objects.filter(operation_key=ONE_TIME_ALL_USERS_RESTART_KEY).exists())

    def test_future_registration_still_starts_separate_trial(self):
        self._apply()
        future = User.objects.create_user(username="future-registrant")
        grant = start_new_user_trial(future)
        self.assertIsNotNone(grant)
        self.assertNotEqual(grant.campaign.operation_key, ONE_TIME_ALL_USERS_RESTART_KEY)
        self.assertEqual(grant.ends_at - grant.started_at, timedelta(days=7))

    def test_command_requires_explicit_confirmation_and_current_digest(self):
        User.objects.create_user(username="command-candidate")
        output = StringIO()
        call_command("restart_all_users_trial_20261029", actor=self.admin.username, stdout=output)
        self.assertIn('"mode": "dry_run"', output.getvalue())
        with self.assertRaises(CommandError):
            call_command("restart_all_users_trial_20261029", actor=self.admin.username, apply=True)
        self.assertFalse(TrialCampaign.objects.filter(operation_key=ONE_TIME_ALL_USERS_RESTART_KEY).exists())

        preview = preview_all_users_trial_restart(actor=self.admin)
        output = StringIO()
        call_command(
            "restart_all_users_trial_20261029", actor=self.admin.username,
            apply=True, confirm_restart_all_users=True,
            expected_eligible_count=preview["eligible_count"],
            expected_candidate_digest=preview["candidate_digest"], stdout=output,
        )
        self.assertIn('"already_applied": false', output.getvalue())
        grants_before = TrialGrant.objects.count()
        output = StringIO()
        call_command(
            "restart_all_users_trial_20261029", actor=self.admin.username,
            apply=True, confirm_restart_all_users=True,
            expected_eligible_count=preview["eligible_count"],
            expected_candidate_digest=preview["candidate_digest"], stdout=output,
        )
        self.assertIn('"already_applied": true', output.getvalue())
        self.assertEqual(TrialGrant.objects.count(), grants_before)

    def test_missing_journey_day_one_blocks_apply(self):
        User.objects.create_user(username="needs-journey")
        TrialJourneyDay.objects.filter(day=1).update(is_active=False)
        with self.assertRaises(TrialCampaignConflict):
            self._apply()
        self.assertFalse(TrialCampaign.objects.filter(operation_key=ONE_TIME_ALL_USERS_RESTART_KEY).exists())
