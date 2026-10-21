from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.notifications.models import (
    SMSAutomationDelivery, SMSAutomationRule, TrialJourneyActivation,
    TrialJourneyDay, TrialJourneyEnrollment,
)

from .market_trial import audit_expired_trials, update_auto_start_settings
from .models import TrialAutoStartDecision, TrialGrant, User, UserAccessAudit


@override_settings(
    MARKET_ACCESS_V2_ENABLED=True, CRM_ENABLED=False,
    SMS_AUTOMATION_ENABLED=True, PAYAMITO_ENABLED=True,
    PAYAMITO_USERNAME="stub-user", PAYAMITO_API_KEY="stub-key",
    PAYAMITO_FROM_NUMBER="5000", TRIAL_JOURNEY_ENABLED=False,
)
class TrialSessionDiagnosticsTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_user(username="trial-admin", role=User.Role.SUPER_ADMIN)

    def register(self, name, *, phone=None):
        data = {
            "username": name, "email": f"{name}@example.org",
            "first_name": "New", "last_name": "Member",
            "password": "StrongPassword!123", "password_confirm": "StrongPassword!123",
        }
        if phone:
            data["phone"] = phone
        test_host = f"203.0.113.{sum(map(ord, name)) % 200 + 1}"
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                "/api/accounts/register/", data, format="json", REMOTE_ADDR=test_host,
            )
        self.assertIn(response.status_code, (200, 201), response.data)
        return User.objects.get(username=name)

    def admin_access(self, user):
        self.client.force_authenticate(self.admin)
        response = self.client.get(
            "/api/accounts/admin/market-access/users/", {"search": user.username},
        )
        self.assertEqual(response.status_code, 200)
        return next(item["access"] for item in response.data["results"] if item["id"] == user.pk)

    def test_disabled_first_session_is_audited_without_trial(self):
        user = self.register("trial-disabled")
        self.assertFalse(TrialGrant.objects.filter(user=user).exists())
        self.assertEqual(TrialAutoStartDecision.objects.get(user=user).reason, "AUTO_START_DISABLED")
        access = self.admin_access(user)
        self.assertEqual(access["trial_status"], "NOT_STARTED")
        self.assertEqual(access["trial_start_blocked_reason"], "AUTO_START_DISABLED")
        self.assertIsNone(access["trial_started_at"])

    def test_enabled_session_starts_once_and_reports_actual_grant(self):
        update_auto_start_settings(actor=self.admin, auto_start_new_users=True)
        rule = SMSAutomationRule.objects.get(slot="WELCOME", market="ALL")
        rule.enabled = True
        rule.save(update_fields=("enabled",))
        user = self.register("trial-once", phone="09121112233")
        grant = TrialGrant.objects.get(user=user)
        self.assertEqual(grant.ends_at - grant.started_at, timedelta(days=7))
        self.assertEqual(grant.source, "AUTO_NEW_USER")
        self.assertEqual(TrialAutoStartDecision.objects.get(user=user).grant_id, grant.pk)
        self.assertEqual(SMSAutomationDelivery.objects.filter(user=user, status="PENDING").count(), 1)
        access = self.admin_access(user)
        self.assertEqual(access["trial_status"], "ACTIVE")
        self.assertEqual(access["trial_source"], "AUTO_NEW_USER")
        self.assertIsNone(access["trial_start_blocked_reason"])
        self.assertEqual(access["trial_started_at"], grant.started_at)
        self.assertEqual(access["trial_ends_at"], grant.ends_at)
        self.assertEqual(audit_expired_trials(now=grant.ends_at - timedelta(seconds=1)), 0)
        now = timezone.now()
        TrialGrant.objects.filter(pk=grant.pk).update(
            started_at=now - timedelta(days=8), ends_at=now - timedelta(days=1),
        )
        self.assertEqual(audit_expired_trials(now=now), 1)
        self.assertEqual(audit_expired_trials(now=now), 0)
        self.assertEqual(UserAccessAudit.objects.filter(
            subject_user_id=user.pk, action=UserAccessAudit.Action.TRIAL_EXPIRED,
        ).count(), 1)
        access = self.admin_access(user)
        self.assertEqual(access["trial_status"], "EXPIRED")
        self.assertFalse(access["trial_active"])

    def test_old_account_is_not_enrolled_by_later_auto_start(self):
        old = User.objects.create_user(username="trial-existing")
        User.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=1))
        update_auto_start_settings(actor=self.admin, auto_start_new_users=True)
        from .market_trial import start_new_user_trial
        self.assertIsNone(start_new_user_trial(old))
        self.assertEqual(TrialAutoStartDecision.objects.get(user=old).reason, "EXISTING_ACCOUNT")
        self.assertFalse(TrialGrant.objects.filter(user=old).exists())

    def test_missing_phone_does_not_rollback_valid_trial(self):
        update_auto_start_settings(actor=self.admin, auto_start_new_users=True)
        rule = SMSAutomationRule.objects.get(slot="WELCOME", market="ALL")
        rule.enabled = True
        rule.save(update_fields=("enabled",))
        user = self.register("trial-no-phone")
        self.assertTrue(TrialGrant.objects.filter(user=user).exists())
        delivery = SMSAutomationDelivery.objects.get(user=user)
        self.assertEqual(delivery.status, "SKIPPED")
        self.assertEqual(delivery.failure_code, "INVALID_OR_MISSING_PHONE")

    def test_disabled_rule_and_provider_are_reported_without_losing_trial(self):
        update_auto_start_settings(actor=self.admin, auto_start_new_users=True)
        no_rule_user = self.register("trial-no-rule", phone="09121112235")
        no_rule = SMSAutomationDelivery.objects.get(user=no_rule_user)
        self.assertEqual((no_rule.status, no_rule.failure_code),
                         ("SKIPPED", "RULE_DISABLED_OR_MISSING"))
        welcome = SMSAutomationRule.objects.get(slot="WELCOME", market="ALL")
        welcome.enabled = True
        welcome.save(update_fields=("enabled",))
        with override_settings(PAYAMITO_ENABLED=False):
            no_provider_user = self.register("trial-no-provider", phone="09121112236")
        no_provider = SMSAutomationDelivery.objects.get(user=no_provider_user)
        self.assertEqual((no_provider.status, no_provider.failure_code),
                         ("SKIPPED", "PROVIDER_NOT_CONFIGURED"))
        self.assertEqual(TrialGrant.objects.filter(user_id__in=(
            no_rule_user.pk, no_provider_user.pk,
        )).count(), 2)

    @override_settings(TRIAL_JOURNEY_ENABLED=True)
    def test_journey_day_one_owns_welcome_and_is_queued_after_commit(self):
        TrialJourneyActivation.objects.create(pk=1, activated_at=timezone.now())
        day_one = TrialJourneyDay.objects.get(day=1)
        day_one.is_active = True
        day_one.in_app_enabled = False
        day_one.push_enabled = False
        day_one.save(update_fields=("is_active", "in_app_enabled", "push_enabled"))
        update_auto_start_settings(actor=self.admin, auto_start_new_users=True)
        welcome = SMSAutomationRule.objects.get(slot="WELCOME", market="ALL")
        welcome.enabled = True
        welcome.save(update_fields=("enabled",))
        user = self.register("trial-journey", phone="09121112234")
        grant = TrialGrant.objects.get(user=user)
        self.assertTrue(TrialJourneyEnrollment.objects.filter(grant=grant).exists())
        deliveries = list(SMSAutomationDelivery.objects.filter(user=user))
        self.assertEqual(len(deliveries), 2)
        self.assertEqual(sum(item.status == "PENDING" for item in deliveries), 1)
        self.assertEqual(sum(item.failure_code == "JOURNEY_OWNS_WELCOME" for item in deliveries), 1)
        self.assertEqual(deliveries[0].user_id, user.pk)
        self.assertIn("New عزیز", next(item.text for item in deliveries if item.status == "PENDING"))

    @override_settings(TRIAL_JOURNEY_ENABLED=True)
    def test_phone_signup_name_is_used_in_day_one_sms(self):
        TrialJourneyActivation.objects.create(pk=1, activated_at=timezone.now())
        update_auto_start_settings(actor=self.admin, auto_start_new_users=True)
        day_one = TrialJourneyDay.objects.get(day=1)
        day_one.is_active = True
        day_one.market = "ALL"
        day_one.text = "{first_name} عزیز، خوش آمدید!"
        day_one.save(update_fields=("is_active", "market", "text"))
        with patch("apps.accounts.otp.secrets.randbelow", return_value=4839), patch(
            "apps.accounts.otp.PayamitoService.send_otp"
        ):
            requested = self.client.post(
                "/api/accounts/auth/registration/request/", {"phone": "09121112239"},
            )
        self.assertEqual(requested.status_code, 200)
        with self.captureOnCommitCallbacks(execute=True):
            verified = self.client.post(
                "/api/accounts/auth/registration/verify/",
                {"phone": "09121112239", "code": "4839", "first_name": "مینا", "last_name": "احمدی"},
            )
        self.assertEqual(verified.status_code, 200)
        user = User.objects.get(phone="09121112239")
        delivery = SMSAutomationDelivery.objects.get(user=user, event="JOURNEY")
        self.assertEqual(delivery.status, "PENDING")
        self.assertEqual(delivery.text, "مینا عزیز، خوش آمدید!")
