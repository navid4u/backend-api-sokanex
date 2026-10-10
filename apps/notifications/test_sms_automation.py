from datetime import timedelta
from unittest.mock import patch
import uuid

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import (
    TrialCampaign, TrialGrant, User, UserAccessAudit, UserMarketGrant,
)
from common.sms import SMSProviderError

from .models import SMSAutomationDelivery, SMSAutomationRule, SMSBroadcast
from .sms_automation import queue_due_trial_messages, queue_event, send_pending


@override_settings(
    MARKET_ACCESS_V2_ENABLED=True,
    PAYAMITO_ENABLED=True,
    PAYAMITO_USERNAME="test-user",
    PAYAMITO_API_KEY="not-a-real-key",
    PAYAMITO_FROM_NUMBER="12345",
    SMS_AUTOMATION_ENABLED=True,
)
class SMSAutomationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="sms-admin", password="Pass123456!", role=User.Role.SUPER_ADMIN,
        )
        self.user = User.objects.create_user(
            username="sms-user", password="Pass123456!", phone="09123456789",
            first_name="علی", market_type="forex",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_rules_are_disabled_by_default_and_user_cannot_manage(self):
        self.assertFalse(SMSAutomationRule.objects.filter(enabled=True).exists())
        self.client.force_authenticate(self.user)
        response = self.client.get("/api/notifications/sms-automation/rules/")
        self.assertEqual(response.status_code, 403)

    def test_welcome_queues_once_and_sends_exact_rendered_text(self):
        rule = SMSAutomationRule.objects.get(slot="WELCOME", market="forex")
        rule.enabled = True
        rule.text = "سلام {first_name}، {support_link}"
        rule.save()
        queue_event(self.user.pk, "WELCOME", "WELCOME:REGISTRATION")
        queue_event(self.user.pk, "WELCOME", "WELCOME:REGISTRATION")
        self.assertEqual(SMSAutomationDelivery.objects.count(), 1)
        with patch("apps.notifications.sms_automation.PayamitoSMSService.send", return_value={"message_id": "42"}) as send:
            with CaptureQueriesContext(connection) as queries:
                self.assertEqual(send_pending(), 1)
        claim_sql = next(
            item["sql"] for item in queries
            if f'FROM "{SMSAutomationDelivery._meta.db_table}"' in item["sql"]
        )
        # Nullable rule/broadcast joins make PostgreSQL reject FOR UPDATE.
        self.assertNotIn(SMSAutomationRule._meta.db_table, claim_sql)
        self.assertNotIn(SMSBroadcast._meta.db_table, claim_sql)
        self.assertIn("علی", send.call_args.args[1])
        self.assertEqual(SMSAutomationDelivery.objects.get().status, "SENT")

    def test_new_registration_triggers_welcome_without_a_second_api_call(self):
        rule = SMSAutomationRule.objects.get(slot="WELCOME", market="ALL")
        rule.enabled = True
        rule.save()
        with self.captureOnCommitCallbacks(execute=True):
            newcomer = User.objects.create_user(
                username="new-sms-user", password="Pass123456!", phone="09123456780",
            )
        self.assertTrue(SMSAutomationDelivery.objects.filter(
            user=newcomer, event_key="WELCOME:REGISTRATION", status="PENDING",
        ).exists())

    def test_trial_days_queue_once_and_skip_after_market_activation(self):
        rule = SMSAutomationRule.objects.get(slot="TRIAL_3", market="ALL")
        rule.enabled = True
        rule.send_time_utc = timezone.datetime.min.time()
        rule.save()
        campaign = TrialCampaign.objects.create(created_by=self.admin, status="APPLIED")
        now = timezone.now()
        grant = TrialGrant.objects.create(
            user=self.user, campaign=campaign,
            started_at=now - timedelta(days=2, hours=2),
            ends_at=now + timedelta(days=4, hours=22),
        )
        self.assertEqual(queue_due_trial_messages(now=now), 1)
        self.assertEqual(queue_due_trial_messages(now=now), 0)
        delivery = SMSAutomationDelivery.objects.get()
        self.assertEqual(delivery.event_key, f"TRIAL:{grant.pk}:TRIAL_3")
        UserMarketGrant.objects.create(
            user=self.user, market="forex", source=UserMarketGrant.Source.ADMIN,
            granted_by=self.admin,
        )
        with patch("apps.notifications.sms_automation.PayamitoSMSService.send") as send:
            self.assertEqual(send_pending(), 0)
        send.assert_not_called()
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, "SKIPPED")

    def test_old_trial_sms_does_not_send_during_new_trial(self):
        rule = SMSAutomationRule.objects.get(slot="TRIAL_3", market="ALL")
        rule.enabled = True
        rule.send_time_utc = timezone.datetime.min.time()
        rule.save()
        now = timezone.now()
        old_campaign = TrialCampaign.objects.create(created_by=self.admin, status="APPLIED")
        old_grant = TrialGrant.objects.create(
            user=self.user, campaign=old_campaign,
            started_at=now - timedelta(days=2, hours=2),
            ends_at=now + timedelta(days=4, hours=22),
        )
        self.assertEqual(queue_due_trial_messages(now=now), 1)
        old_grant.invalidated_at = now
        old_grant.revoked_at = now
        old_grant.save(update_fields=("invalidated_at", "revoked_at"))
        new_campaign = TrialCampaign.objects.create(created_by=self.admin, status="APPLIED")
        TrialGrant.objects.create(
            user=self.user, campaign=new_campaign,
            started_at=now, ends_at=now + timedelta(days=7),
        )
        with patch("apps.notifications.sms_automation.PayamitoSMSService.send") as send:
            self.assertEqual(send_pending(), 0)
        send.assert_not_called()
        self.assertEqual(SMSAutomationDelivery.objects.get().status, "SKIPPED")

    def test_rule_validation_and_patch(self):
        rule = SMSAutomationRule.objects.get(slot="TRIAL_1", market="ALL")
        url = f"/api/notifications/sms-automation/rules/{rule.pk}/"
        self.assertEqual(self.client.patch(url, {"text": "{user.password}"}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(url, {"trial_day": 8}, format="json").status_code, 400)
        response = self.client.patch(url, {"enabled": True, "send_time_utc": "07:30:00"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["enabled"])
        self.assertIsNotNone(response.data["enabled_at"])

    def test_broadcast_preview_confirm_and_stale_rejection(self):
        url = "/api/notifications/sms-automation/broadcasts/preview/"
        body = {"membership_tiers": ["LEVEL_1"], "market": "ALL", "text": "سلام {first_name}"}
        preview = self.client.post(url, body, format="json")
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.data["eligible_count"], 1)
        send_body = {
            **body, "expected_eligible_count": 1,
            "expected_candidate_digest": preview.data["candidate_digest"], "confirm": True,
            "idempotency_key": "broadcast-test-1",
        }
        self.assertEqual(self.client.post(
            "/api/notifications/sms-automation/broadcasts/send/",
            {**send_body, "expected_eligible_count": 2}, format="json",
        ).status_code, 409)
        self.assertFalse(SMSBroadcast.objects.exists())
        response = self.client.post("/api/notifications/sms-automation/broadcasts/send/", send_body, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(SMSAutomationDelivery.objects.filter(broadcast__isnull=False).count(), 1)
        self.assertEqual(self.client.post("/api/notifications/sms-automation/broadcasts/send/", send_body, format="json").status_code, 200)
        self.assertEqual(SMSAutomationDelivery.objects.filter(broadcast__isnull=False).count(), 1)

    def test_delivery_log_is_paginated_and_private(self):
        self.client.post(
            "/api/notifications/sms-automation/broadcasts/preview/",
            {"membership_tiers": ["LEVEL_1"], "market": "ALL", "text": "سلام"}, format="json",
        )
        response = self.client.get("/api/notifications/sms-automation/deliveries/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("results", response.data)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get("/api/notifications/sms-automation/deliveries/").status_code, 403)

    def test_access_change_audits_dedupe_one_operation(self):
        rule = SMSAutomationRule.objects.get(slot="ACCESS_CHANGE", market="ALL")
        rule.enabled = True
        rule.save()
        operation_id = uuid.uuid4()
        with self.captureOnCommitCallbacks(execute=True):
            for market in ("forex", "crypto"):
                UserAccessAudit.objects.create(
                    user=self.user, subject_user_id=self.user.pk, actor=self.admin,
                    action=UserAccessAudit.Action.MARKET_GRANTED,
                    before={"market": market, "active": False},
                    after={"market": market, "active": True},
                    operation_id=operation_id,
                )
        self.assertEqual(SMSAutomationDelivery.objects.filter(event="ACCESS_CHANGE").count(), 1)

    def test_provider_failure_is_recorded_without_automatic_retry(self):
        rule = SMSAutomationRule.objects.get(slot="WELCOME", market="ALL")
        rule.enabled = True
        rule.save()
        queue_event(self.user.pk, "WELCOME", "WELCOME:REGISTRATION")
        with patch("apps.notifications.sms_automation.PayamitoSMSService.send", side_effect=SMSProviderError("unavailable", provider_code="TEST_FAIL")) as send:
            self.assertEqual(send_pending(), 0)
            self.assertEqual(send_pending(), 0)
        self.assertEqual(send.call_count, 1)
        delivery = SMSAutomationDelivery.objects.get()
        self.assertEqual(delivery.status, "FAILED")
        self.assertEqual(delivery.failure_code, "TEST_FAIL")

    @override_settings(SMS_AUTOMATION_ENABLED=False)
    def test_global_kill_switch_does_not_queue_or_send(self):
        rule = SMSAutomationRule.objects.get(slot="WELCOME", market="ALL")
        rule.enabled = True
        rule.save()
        queue_event(self.user.pk, "WELCOME", "WELCOME:REGISTRATION")
        self.assertFalse(SMSAutomationDelivery.objects.exists())
        self.assertEqual(send_pending(), 0)
        self.assertEqual(self.client.post(
            "/api/notifications/sms-automation/broadcasts/send/", {}, format="json",
        ).status_code, 409)
