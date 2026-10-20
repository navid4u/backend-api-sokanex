from datetime import timedelta
from unittest.mock import patch
import uuid

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import (
    TrialCampaign, TrialGrant, User, UserAccessAudit, UserAccessProfile,
    UserMarketGrant, UserMarketPreference,
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

    def _broadcast_members(self):
        def make(username, phone, markets=(), *, selected=(), elite=False, active=True):
            user = User.objects.create_user(username=username, phone=phone, is_active=active)
            for market in markets:
                UserMarketGrant.objects.create(
                    user=user, market=market, source=UserMarketGrant.Source.ADMIN,
                    granted_by=self.admin,
                )
            for market in selected:
                UserMarketPreference.objects.create(user=user, market=market)
            if elite:
                UserAccessProfile.objects.update_or_create(user=user, defaults={"is_elite": True})
            return user

        basic = make("sms-basic", "09120000001", ("crypto",), selected=("crypto",))
        pro = make("sms-pro", "09120000002", ("forex", "internal"), selected=("forex",))
        pro_elite = make(
            "sms-pro-elite", "09120000003", ("forex", "internal"),
            selected=("internal",), elite=True,
        )
        gold = make(
            "sms-gold", "09120000004", ("crypto", "forex", "internal"),
            selected=("crypto",),
        )
        make("sms-inactive-pro", "09120000005", ("forex", "internal"), active=False)
        make("sms-missing-phone-pro", None, ("forex", "internal"))
        invalid = make("sms-invalid-phone-pro", "09120000006", ("forex", "internal"))
        User.objects.filter(pk=invalid.pk).update(phone="invalid-legacy-phone")
        campaign = TrialCampaign.objects.create(created_by=self.admin, status="APPLIED")
        TrialGrant.objects.create(
            user=self.user, campaign=campaign,
            started_at=timezone.now() - timedelta(days=1),
            ends_at=timezone.now() + timedelta(days=6),
        )
        return basic, pro, pro_elite, gold

    def _preview(self, tiers, market="ALL"):
        return self.client.post(
            "/api/notifications/sms-automation/broadcasts/preview/",
            {"membership_tiers": tiers, "market": market, "text": "سلام"},
            format="json",
        )

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
            response = self.client.post("/api/accounts/register/", {
                "username": "new-sms-user", "phone": "09123456780",
                "first_name": "New", "last_name": "Member",
                "password": "Pass123456!", "password_confirm": "Pass123456!",
            }, format="json")
        self.assertIn(response.status_code, (200, 201))
        newcomer = User.objects.get(username="new-sms-user")
        self.assertTrue(SMSAutomationDelivery.objects.filter(
            user=newcomer, event_key=f"WELCOME:REGISTRATION:{newcomer.pk}", status="PENDING",
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

    def test_broadcast_tiers_elite_union_market_and_exclusion_diagnostics(self):
        _, pro, _, _ = self._broadcast_members()
        expected = {"LEVEL_1": 1, "BASIC": 1, "PRO": 2, "GOLD": 1, "ELITE": 1}
        for tier, count in expected.items():
            with self.subTest(tier=tier):
                response = self._preview([tier])
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data["eligible_count"], count)
        pro_preview = self._preview(["PRO"])
        self.assertEqual(pro_preview.data["diagnostics"], {
            "matched_count": 5,
            "excluded_counts": {"inactive": 1, "missing_phone": 1, "invalid_phone": 1},
        })
        self.assertEqual(pro_preview.data["diagnostics"]["matched_count"],
                         pro_preview.data["eligible_count"] + 3)
        self.assertEqual(self._preview(["PRO", "ELITE"]).data["eligible_count"], 2)
        self.assertEqual(self._preview(["PRO"], "forex").data["eligible_count"], 1)
        self.assertEqual(self._preview(["PRO"], "internal").data["eligible_count"], 1)
        self.assertEqual(self._preview(["PRO"], "crypto").data["eligible_count"], 0)
        self.assertEqual(self._preview(["BASIC"], "crypto").data["eligible_count"], 1)
        self.assertEqual(self._preview(["GOLD"], "crypto").data["eligible_count"], 1)
        self.assertEqual(self._preview(["LEVEL_1"], "ALL").data["eligible_count"], 1)
        self.client.force_authenticate(pro)
        profile = self.client.get("/api/accounts/profile/")
        self.assertEqual(profile.data["market_access_v2"]["membership_tier"], "PRO")
        dashboard = self.client.get("/api/dashboard/")
        self.assertEqual(dashboard.data["data"]["market_access_v2"]["membership_tier"], "PRO")
        self.assertEqual(self._preview(["PRO"]).status_code, 403)
        self.client.force_authenticate(self.admin)
        admin_detail = self.client.get(f"/api/accounts/admin/market-access/users/{pro.pk}/")
        self.assertEqual(admin_detail.data["access"]["membership_tier"], "PRO")

    def test_broadcast_send_uses_preview_union_and_rejects_changed_audience(self):
        self._broadcast_members()
        preview = self._preview(["PRO", "ELITE"])
        self.assertEqual(preview.data["eligible_count"], 2)
        body = {
            "membership_tiers": ["PRO", "ELITE"], "market": "ALL", "text": "سلام",
            "expected_eligible_count": preview.data["eligible_count"],
            "expected_candidate_digest": preview.data["candidate_digest"],
            "confirm": True, "idempotency_key": "pro-elite-audience-1",
        }
        send_url = "/api/notifications/sms-automation/broadcasts/send/"
        self.assertEqual(self.client.post(send_url, body, format="json").status_code, 201)
        self.assertEqual(SMSAutomationDelivery.objects.filter(broadcast__isnull=False).count(), 2)
        self.assertEqual(self.client.post(send_url, body, format="json").status_code, 200)
        self.assertEqual(SMSAutomationDelivery.objects.filter(broadcast__isnull=False).count(), 2)
        stale = self._preview(["PRO"])
        User.objects.filter(username="sms-pro").update(is_active=False)
        changed = self.client.post(send_url, {
            "membership_tiers": ["PRO"], "market": "ALL", "text": "سلام",
            "expected_eligible_count": stale.data["eligible_count"],
            "expected_candidate_digest": stale.data["candidate_digest"],
            "confirm": True, "idempotency_key": "pro-audience-stale-1",
        }, format="json")
        self.assertEqual(changed.status_code, 409)
        self.assertEqual(changed.data["code"], "AUDIENCE_CHANGED")
        self.assertEqual(SMSBroadcast.objects.count(), 1)

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
        self.assertEqual(SMSAutomationDelivery.objects.get().status, "SKIPPED")
        self.assertEqual(SMSAutomationDelivery.objects.get().failure_code, "AUTOMATION_DISABLED")
        self.assertEqual(send_pending(), 0)
        self.assertEqual(self.client.post(
            "/api/notifications/sms-automation/broadcasts/send/", {}, format="json",
        ).status_code, 409)

    def test_legacy_expiry_message_waits_for_exact_trial_end(self):
        rule = SMSAutomationRule.objects.get(slot="TRIAL_7", market="ALL")
        rule.enabled = True
        rule.send_time_utc = timezone.datetime.min.time()
        rule.save(update_fields=("enabled", "send_time_utc"))
        now = timezone.now()
        campaign = TrialCampaign.objects.create(created_by=self.admin, status="APPLIED")
        grant = TrialGrant.objects.create(
            user=self.user, campaign=campaign,
            started_at=now - timedelta(days=7), ends_at=now,
        )
        self.assertEqual(queue_due_trial_messages(now=now - timedelta(seconds=1)), 0)
        self.assertEqual(queue_due_trial_messages(now=now), 1)
        delivery = SMSAutomationDelivery.objects.get(event_key=f"TRIAL:{grant.pk}:TRIAL_7")
        self.assertGreaterEqual(delivery.scheduled_at, grant.ends_at)
        with patch("apps.notifications.sms_automation.PayamitoSMSService.send", return_value={"message_id": "stub"}):
            self.assertEqual(send_pending(), 1)
        self.assertEqual(delivery.user.pk, self.user.pk)

    def test_delivery_filters_ordering_and_error_snapshot(self):
        now = timezone.now()
        for index, status in enumerate(("PENDING", "FAILED", "SENT")):
            delivery = SMSAutomationDelivery.objects.create(
                user=self.user, event_key=f"REPORT:{index}", event="TEST",
                phone="09123456789", text=f"snapshot {index}", status=status,
                scheduled_at=now, sent_at=now if status == "SENT" else None,
                failure_code="STUB_FAILURE" if status == "FAILED" else "",
            )
            SMSAutomationDelivery.objects.filter(pk=delivery.pk).update(
                created_at=now + timedelta(minutes=index),
            )
        url = "/api/notifications/sms-automation/deliveries/"
        response = self.client.get(url, {"user_id": self.user.pk, "page_size": 2, "ordering": "-created_at"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 3)
        self.assertEqual(len(response.data["results"]), 2)
        self.assertEqual(response.data["results"][0]["rendered_text"], "snapshot 2")
        failed = self.client.get(url, {"user_id": self.user.pk, "status": "FAILED", "ordering": "-sent_at"})
        self.assertEqual(failed.data["count"], 1)
        self.assertEqual(failed.data["results"][0]["error_code"], "STUB_FAILURE")
        self.assertEqual(self.client.get(url, {"ordering": "wrong"}).status_code, 400)
