from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.market_trial import ONE_TIME_ALL_USERS_RESTART_KEY, TrialCampaignConflict
from apps.accounts.models import TrialCampaign, TrialGrant, User

from .models import SMSAutomationDelivery, TrialJourneyDay, TrialJourneyDispatch, TrialJourneyEnrollment
from .sms_automation import _still_eligible
from .trial_day_three_cancel import CANCEL_CODE
from .trial_day_three_reissue import (
    REISSUE_EVENT, apply_day_three_reissue, preview_day_three_reissue,
)


@override_settings(MARKET_ACCESS_V2_ENABLED=True, TRIAL_JOURNEY_ENABLED=True, CRM_ENABLED=False)
class DayThreeReissueTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="day3-admin", role=User.Role.SUPER_ADMIN)
        self.campaign = TrialCampaign.objects.create(
            created_by=self.admin, operation_key=ONE_TIME_ALL_USERS_RESTART_KEY,
            status=TrialCampaign.Status.APPLIED, applied_at=timezone.now(),
        )
        self.rule, _ = TrialJourneyDay.objects.update_or_create(
            day=3, defaults={
                "is_active": True,
                "text": "Updated day three for {first_name}",
            },
        )

    def _source(self, username, *, status="SKIPPED", reason=CANCEL_CODE):
        user = User.objects.create_user(
            username=username, first_name=username,
            phone=f"0912{User.objects.count():07d}",
        )
        now = timezone.now()
        grant = TrialGrant.objects.create(
            user=user, campaign=self.campaign,
            started_at=now - timedelta(days=2), ends_at=now + timedelta(days=5),
        )
        enrollment = TrialJourneyEnrollment.objects.create(grant=grant)
        delivery = SMSAutomationDelivery.objects.create(
            user=user, event_key=f"JOURNEY:{grant.pk}:3:SMS", event="JOURNEY",
            phone=user.phone, text="Original day-three SMS", status=status,
            failure_code=reason if status == "SKIPPED" else "",
            provider_message_id="accepted-id" if status == "SENT" else "",
            sent_at=now if status == "SENT" else None,
            scheduled_at=now - timedelta(minutes=1),
        )
        TrialJourneyDispatch.objects.create(
            enrollment=enrollment, day=3, channel="SMS", sms_delivery=delivery,
            status="SKIPPED" if status == "SKIPPED" else "DISPATCHED",
        )
        return user, grant, delivery

    def _apply(self):
        preview = preview_day_three_reissue(actor=self.admin)
        return apply_day_three_reissue(
            actor=self.admin, expected_count=preview["source_cancelled_count"],
            expected_candidate_digest=preview["candidate_digest"],
            expected_template_digest=preview["template_digest"],
        )

    def test_only_cancelled_unsent_users_receive_new_frozen_message(self):
        cancelled_user, cancelled_grant, original = self._source("cancelled")
        sent_user, _, sent_original = self._source("already-sent", status="SENT")
        self._source("other-skip", reason="INVALID_OR_MISSING_PHONE")
        preview = preview_day_three_reissue(actor=self.admin)
        self.assertEqual(preview["source_cancelled_count"], 1)
        self.assertEqual(preview["new_pending_count"], 1)
        self.assertEqual(preview["original_day_three_sent_preserved"], 1)
        result = self._apply()
        self.assertEqual(result["new_pending"], 1)
        self.assertEqual(SMSAutomationDelivery.objects.filter(event=REISSUE_EVENT).count(), 1)
        reissue = SMSAutomationDelivery.objects.get(event=REISSUE_EVENT)
        self.assertEqual(reissue.user_id, cancelled_user.pk)
        self.assertEqual(reissue.text, "Updated day three for cancelled")
        self.assertEqual(reissue.status, "PENDING")
        self.assertTrue(_still_eligible(reissue, now=timezone.now()))
        original.refresh_from_db()
        sent_original.refresh_from_db()
        self.assertEqual((original.status, original.failure_code), ("SKIPPED", CANCEL_CODE))
        self.assertEqual((sent_original.status, sent_original.provider_message_id), ("SENT", "accepted-id"))
        self.assertFalse(SMSAutomationDelivery.objects.filter(event=REISSUE_EVENT, user=sent_user).exists())
        self.assertEqual(TrialGrant.objects.get(pk=cancelled_grant.pk).ends_at, cancelled_grant.ends_at)
        self.assertTrue(self._apply()["already_applied"])

    def test_changed_audience_or_text_refuses_without_queueing(self):
        self._source("cancelled")
        preview = preview_day_three_reissue(actor=self.admin)
        self.rule.text = "Another corrected text"
        self.rule.save(update_fields=("text", "updated_at"))
        with self.assertRaises(TrialCampaignConflict):
            apply_day_three_reissue(
                actor=self.admin, expected_count=preview["source_cancelled_count"],
                expected_candidate_digest=preview["candidate_digest"],
                expected_template_digest=preview["template_digest"],
            )
        self.assertFalse(SMSAutomationDelivery.objects.filter(event=REISSUE_EVENT).exists())
        preview = preview_day_three_reissue(actor=self.admin)
        self._source("later-cancelled")
        with self.assertRaises(TrialCampaignConflict):
            apply_day_three_reissue(
                actor=self.admin, expected_count=preview["source_cancelled_count"],
                expected_candidate_digest=preview["candidate_digest"],
                expected_template_digest=preview["template_digest"],
            )

    def test_command_requires_explicit_confirmations_and_stopped_worker(self):
        self._source("cancelled")
        output = StringIO()
        call_command("reissue_trial_day_three_sms_20261029", actor=self.admin.username, stdout=output)
        self.assertIn('"mode": "dry_run"', output.getvalue())
        with self.assertRaises(CommandError):
            call_command("reissue_trial_day_three_sms_20261029", actor=self.admin.username, apply=True)
        preview = preview_day_three_reissue(actor=self.admin)
        with patch("apps.notifications.management.commands.reissue_trial_day_three_sms_20261029._require_stopped_worker"):
            call_command(
                "reissue_trial_day_three_sms_20261029", actor=self.admin.username,
                apply=True, confirm_send_to_cancelled_only=True,
                confirm_worker_stopped=True,
                expected_count=preview["source_cancelled_count"],
                expected_candidate_digest=preview["candidate_digest"],
                expected_template_digest=preview["template_digest"], stdout=StringIO(),
            )
        self.assertEqual(SMSAutomationDelivery.objects.filter(event=REISSUE_EVENT).count(), 1)
