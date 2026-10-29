from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.market_trial import ONE_TIME_ALL_USERS_RESTART_KEY, TrialCampaignConflict
from apps.accounts.models import TrialCampaign, TrialGrant, User

from .models import SMSAutomationDelivery, TrialJourneyActivation, TrialJourneyDay
from .sms_automation import _still_eligible
from .trial_day_one_reissue import (
    REISSUE_EVENT, SUPERSEDED_CODE, apply_day_one_reissue,
    preview_day_one_reissue,
)


@override_settings(MARKET_ACCESS_V2_ENABLED=True, TRIAL_JOURNEY_ENABLED=True, CRM_ENABLED=False)
class DayOneReissueTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="reissue-admin", role=User.Role.SUPER_ADMIN)
        now = timezone.now()
        self.campaign = TrialCampaign.objects.create(
            created_by=self.admin, operation_key=ONE_TIME_ALL_USERS_RESTART_KEY,
            status=TrialCampaign.Status.APPLIED, applied_at=now,
        )
        TrialJourneyActivation.objects.create(pk=1, activated_at=now - timedelta(days=1))
        TrialJourneyDay.objects.update_or_create(
            day=1, defaults={"is_active": True, "text": "New day-one for {first_name}"},
        )

    def _user(self, username, phone, *, active=True, old_status=None):
        user = User.objects.create_user(
            username=username, first_name=username, phone=phone, is_active=active,
        )
        now = timezone.now()
        grant = TrialGrant.objects.create(
            user=user, campaign=self.campaign, started_at=now - timedelta(minutes=5),
            ends_at=now + timedelta(days=7) - timedelta(minutes=5),
        )
        if old_status:
            SMSAutomationDelivery.objects.create(
                user=user, event_key=f"JOURNEY:{grant.pk}:1:SMS", event="JOURNEY",
                phone=phone or "", text="Old day-one message" if phone else "",
                status=old_status, scheduled_at=now - timedelta(minutes=5),
                provider_message_id="accepted-id" if old_status == "SENT" else "",
            )
        return user, grant

    def _apply(self):
        preview = preview_day_one_reissue(actor=self.admin)
        return apply_day_one_reissue(
            actor=self.admin,
            expected_pending_count=preview["original_pending_to_supersede"],
            expected_candidate_digest=preview["candidate_digest"],
            expected_template_digest=preview["template_digest"],
        )

    def test_corrected_text_requeues_every_sendable_user_without_mutating_sent_history(self):
        sent_user, sent_grant = self._user("already-sent", "09120000001", old_status="SENT")
        queued_user, queued_grant = self._user("old-pending", "09120000002", old_status="PENDING")
        self._user("no-phone", "", old_status="SKIPPED")
        self._user("inactive", "09120000004", active=False)
        preview = preview_day_one_reissue(actor=self.admin)
        self.assertEqual(preview["cohort_size"], 4)
        self.assertEqual(preview["new_pending_count"], 2)
        self.assertEqual(preview["original_sent_will_receive_second_sms"], 1)
        self.assertEqual(preview["original_pending_to_supersede"], 1)
        self.assertEqual(preview["new_skipped_by_reason"], {
            "INVALID_OR_MISSING_PHONE": 1, "USER_INACTIVE": 1,
        })
        result = self._apply()
        self.assertEqual(result["new_pending"], 2)
        self.assertEqual(result["old_pending_superseded"], 1)
        old_sent = SMSAutomationDelivery.objects.get(user=sent_user, event="JOURNEY")
        old_pending = SMSAutomationDelivery.objects.get(user=queued_user, event="JOURNEY")
        self.assertEqual(old_sent.status, "SENT")
        self.assertEqual(old_sent.provider_message_id, "accepted-id")
        self.assertEqual(old_pending.status, "SKIPPED")
        self.assertEqual(old_pending.failure_code, SUPERSEDED_CODE)
        reissues = SMSAutomationDelivery.objects.filter(event=REISSUE_EVENT)
        self.assertEqual(reissues.count(), 4)
        self.assertEqual(reissues.filter(status="PENDING").count(), 2)
        self.assertEqual(reissues.get(user=sent_user).text, "New day-one for already-sent")
        self.assertTrue(_still_eligible(reissues.get(user=queued_user), now=timezone.now()))
        self.assertEqual(TrialGrant.objects.get(pk=sent_grant.pk).ends_at, sent_grant.ends_at)
        self.assertEqual(TrialGrant.objects.get(pk=queued_grant.pk).ends_at, queued_grant.ends_at)
        self.assertTrue(self._apply()["already_applied"])
        self.assertEqual(reissues.count(), 4)

    def test_stale_preview_and_unchanged_text_refuse_without_cancelling_pending(self):
        user, _ = self._user("pending-user", "09120000005", old_status="PENDING")
        TrialJourneyDay.objects.filter(day=1).update(text="Old day-one message")
        with self.assertRaises(TrialCampaignConflict):
            self._apply()
        self.assertEqual(SMSAutomationDelivery.objects.get(user=user).status, "PENDING")
        TrialJourneyDay.objects.filter(day=1).update(text="New corrected text")
        preview = preview_day_one_reissue(actor=self.admin)
        TrialJourneyDay.objects.filter(day=1).update(text="Another edit")
        with self.assertRaises(TrialCampaignConflict):
            apply_day_one_reissue(
                actor=self.admin,
                expected_pending_count=preview["original_pending_to_supersede"],
                expected_candidate_digest=preview["candidate_digest"],
                expected_template_digest=preview["template_digest"],
            )
        self.assertEqual(SMSAutomationDelivery.objects.get(user=user).status, "PENDING")

    def test_sending_original_blocks_resend(self):
        user, _ = self._user("ambiguous-user", "09120000006", old_status="SENDING")
        with self.assertRaises(TrialCampaignConflict):
            self._apply()
        self.assertFalse(SMSAutomationDelivery.objects.filter(user=user, event=REISSUE_EVENT).exists())

    def test_failure_during_reissue_rolls_back_old_pending_cancellation(self):
        user, _ = self._user("rollback-user", "09120000008", old_status="PENDING")
        with patch("apps.notifications.trial_day_one_reissue.SMSAutomationDelivery.objects.bulk_create",
                   side_effect=RuntimeError("simulated database failure")):
            with self.assertRaises(RuntimeError):
                self._apply()
        self.assertEqual(SMSAutomationDelivery.objects.get(user=user).status, "PENDING")
        self.assertFalse(SMSAutomationDelivery.objects.filter(event=REISSUE_EVENT).exists())

    def test_command_dry_run_shows_text_but_apply_requires_explicit_flags(self):
        self._user("command-user", "09120000007", old_status="SENT")
        output = StringIO()
        call_command("reissue_trial_day_one_sms_20261029", actor=self.admin.username, stdout=output)
        self.assertIn("New day-one for {first_name}", output.getvalue())
        with self.assertRaises(CommandError):
            call_command("reissue_trial_day_one_sms_20261029", actor=self.admin.username, apply=True)
        self.assertFalse(SMSAutomationDelivery.objects.filter(event=REISSUE_EVENT).exists())
        preview = preview_day_one_reissue(actor=self.admin)
        output = StringIO()
        with patch("apps.notifications.management.commands.reissue_trial_day_one_sms_20261029._require_stopped_worker"):
            call_command(
                "reissue_trial_day_one_sms_20261029", actor=self.admin.username,
                apply=True, confirm_resend_to_previous_recipients=True,
                confirm_worker_stopped=True,
                expected_old_pending=preview["original_pending_to_supersede"],
                expected_candidate_digest=preview["candidate_digest"],
                expected_template_digest=preview["template_digest"], stdout=output,
            )
        self.assertIn('"already_applied": false', output.getvalue())
