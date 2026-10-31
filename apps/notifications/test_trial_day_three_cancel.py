from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.market_trial import ONE_TIME_ALL_USERS_RESTART_KEY, TrialCampaignConflict
from apps.accounts.models import TrialCampaign, TrialGrant, User

from .models import SMSAutomationDelivery, TrialJourneyDispatch, TrialJourneyEnrollment
from .trial_day_three_cancel import (
    CANCEL_CODE, apply_day_three_cancel, preview_day_three_cancel,
)


@override_settings(MARKET_ACCESS_V2_ENABLED=True, TRIAL_JOURNEY_ENABLED=True, CRM_ENABLED=False)
class DayThreeCancelTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="cancel-admin", role=User.Role.SUPER_ADMIN)
        self.campaign = TrialCampaign.objects.create(
            created_by=self.admin, operation_key=ONE_TIME_ALL_USERS_RESTART_KEY,
            status=TrialCampaign.Status.APPLIED, applied_at=timezone.now(),
        )

    def _delivery(self, username, *, day=3, status="PENDING", campaign=None):
        user = User.objects.create_user(
            username=username, phone=f"0912{User.objects.count():07d}",
        )
        grant = TrialGrant.objects.create(
            user=user, campaign=campaign or self.campaign,
            started_at=timezone.now() - timedelta(days=2),
            ends_at=timezone.now() + timedelta(days=5),
        )
        enrollment = TrialJourneyEnrollment.objects.create(grant=grant)
        delivery = SMSAutomationDelivery.objects.create(
            user=user, event_key=f"JOURNEY:{grant.pk}:{day}:SMS", event="JOURNEY",
            phone=user.phone, text="Original SMS", status=status,
            scheduled_at=timezone.now() - timedelta(minutes=1),
            provider_message_id="accepted-id" if status == "SENT" else "",
            sent_at=timezone.now() if status == "SENT" else None,
        )
        dispatch = TrialJourneyDispatch.objects.create(
            enrollment=enrollment, day=day, channel="SMS", sms_delivery=delivery,
        )
        return delivery, dispatch

    def test_only_pending_day_three_is_cancelled_and_history_preserved(self):
        pending, dispatch = self._delivery("queued")
        sent, _ = self._delivery("sent", status="SENT")
        other_day, _ = self._delivery("other-day", day=5)
        other_campaign = TrialCampaign.objects.create(created_by=self.admin)
        other_cohort, _ = self._delivery("other-campaign", campaign=other_campaign)
        preview = preview_day_three_cancel(actor=self.admin)
        self.assertEqual(preview["pending_to_cancel"], 1)
        self.assertEqual(preview["sent_preserved"], 1)
        result = apply_day_three_cancel(
            actor=self.admin, expected_pending_count=preview["pending_to_cancel"],
            expected_pending_digest=preview["pending_digest"],
        )
        self.assertEqual(result["cancelled_now"], 1)
        pending.refresh_from_db()
        dispatch.refresh_from_db()
        sent.refresh_from_db()
        self.assertEqual((pending.status, pending.failure_code), ("SKIPPED", CANCEL_CODE))
        self.assertEqual(dispatch.status, "SKIPPED")
        self.assertEqual((sent.status, sent.provider_message_id), ("SENT", "accepted-id"))
        for untouched in (other_day, other_cohort):
            untouched.refresh_from_db()
            self.assertEqual(untouched.status, "PENDING")
        again = preview_day_three_cancel(actor=self.admin)
        self.assertEqual(apply_day_three_cancel(
            actor=self.admin, expected_pending_count=0,
            expected_pending_digest=again["pending_digest"],
        )["cancelled_now"], 0)

    def test_stale_preview_and_sending_refuse_without_changes(self):
        pending, _ = self._delivery("queued")
        preview = preview_day_three_cancel(actor=self.admin)
        self._delivery("newly-queued")
        with self.assertRaises(TrialCampaignConflict):
            apply_day_three_cancel(
                actor=self.admin, expected_pending_count=preview["pending_to_cancel"],
                expected_pending_digest=preview["pending_digest"],
            )
        self._delivery("in-flight", status="SENDING")
        current = preview_day_three_cancel(actor=self.admin)
        with self.assertRaises(TrialCampaignConflict):
            apply_day_three_cancel(
                actor=self.admin, expected_pending_count=current["pending_to_cancel"],
                expected_pending_digest=current["pending_digest"],
            )
        pending.refresh_from_db()
        self.assertEqual(pending.status, "PENDING")

    def test_command_requires_explicit_apply_and_stopped_worker(self):
        pending, _ = self._delivery("queued")
        output = StringIO()
        call_command("cancel_trial_day_three_sms_20261029", actor=self.admin.username, stdout=output)
        self.assertIn('"mode": "dry_run"', output.getvalue())
        with self.assertRaises(CommandError):
            call_command("cancel_trial_day_three_sms_20261029", actor=self.admin.username, apply=True)
        preview = preview_day_three_cancel(actor=self.admin)
        with patch("apps.notifications.management.commands.cancel_trial_day_three_sms_20261029._require_stopped_worker"):
            call_command(
                "cancel_trial_day_three_sms_20261029", actor=self.admin.username,
                apply=True, confirm_worker_stopped=True,
                expected_pending_count=preview["pending_to_cancel"],
                expected_pending_digest=preview["pending_digest"], stdout=StringIO(),
            )
        pending.refresh_from_db()
        self.assertEqual(pending.status, "SKIPPED")
