import json
from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import TrialCampaign, TrialGrant, User

from .models import (
    Notification, SMSAutomationDelivery, SMSAutomationRule, TrialJourneyActivation,
    TrialJourneyDay, TrialJourneyDispatch, TrialJourneyEnrollment,
)
from .trial_journey import enroll_new_grants, queue_due_trial_journey, scheduled_at


@override_settings(MARKET_ACCESS_V2_ENABLED=True, CRM_ENABLED=False)
class TrialJourneyTests(APITestCase):
    url = "/api/notifications/sms-automation/journey/"

    def setUp(self):
        self.admin = User.objects.create_user(username="journey-owner", role=User.Role.SUPER_ADMIN)
        self.user = User.objects.create_user(username="journey-user", phone="09120000001")

    def test_configuration_is_exactly_seven_persistent_days(self):
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.force_authenticate(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["day"] for item in response.data["days"]], list(range(1, 8)))
        days = response.data["days"]
        self.assertFalse(days[1]["is_active"])
        self.assertFalse(days[5]["is_active"])
        days[1]["text"] = "پیام روز دوم"
        days[1]["is_active"] = True
        result = self.client.put(self.url, {"days": days}, format="json")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.client.get(self.url).data, result.data)
        self.assertEqual(TrialJourneyDay.objects.get(day=2).text, "پیام روز دوم")
        invalid = self.client.put(self.url, {"days": days[:6]}, format="json")
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(TrialJourneyDay.objects.get(day=2).text, "پیام روز دوم")

    @override_settings(
        TRIAL_JOURNEY_ENABLED=True, SMS_AUTOMATION_ENABLED=True,
        PAYAMITO_ENABLED=True, PAYAMITO_USERNAME="stub-user",
        PAYAMITO_API_KEY="stub-key", PAYAMITO_FROM_NUMBER="5000",
    )
    def test_enrolled_trial_queues_one_sms_and_in_app_without_provider_call(self):
        now = timezone.now()
        TrialJourneyActivation.objects.create(pk=1, activated_at=now - timedelta(seconds=1))
        campaign = TrialCampaign.objects.create(created_by=self.admin)
        grant = TrialGrant.objects.create(
            user=self.user, campaign=campaign, started_at=now,
            ends_at=now + timedelta(days=7),
        )
        enroll_new_grants(user_ids=[self.user.pk], campaign=campaign, started_at=now)
        self.assertTrue(TrialJourneyEnrollment.objects.filter(grant=grant).exists())
        count = queue_due_trial_journey(now=now + timedelta(seconds=2))
        self.assertEqual(count, 2)
        self.assertEqual(Notification.objects.filter(recipient=self.user, show_in_app=True).count(), 1)
        self.assertEqual(SMSAutomationDelivery.objects.filter(user=self.user, status="PENDING").count(), 1)
        self.assertEqual(queue_due_trial_journey(now=now + timedelta(seconds=3)), 0)
        self.assertEqual(TrialJourneyDispatch.objects.filter(enrollment__grant=grant, day=1).count(), 3)

    def test_day_seven_never_precedes_exact_expiry(self):
        now = timezone.now()
        campaign = TrialCampaign.objects.create(created_by=self.admin)
        grant = TrialGrant.objects.create(
            user=self.user, campaign=campaign, started_at=now,
            ends_at=now + timedelta(days=7),
        )
        rule = TrialJourneyDay.objects.get(day=7)
        self.assertGreaterEqual(scheduled_at(grant, rule), grant.ends_at)

    @override_settings(TRIAL_JOURNEY_ENABLED=True)
    def test_activation_preserves_welcome_rule_and_pending_welcome(self):
        welcome = SMSAutomationRule.objects.get(slot="WELCOME", market="ALL")
        welcome.enabled = True
        welcome.save(update_fields=("enabled",))
        trial = SMSAutomationRule.objects.get(slot="TRIAL_1", market="ALL")
        trial.enabled = True
        trial.save(update_fields=("enabled",))
        now = timezone.now()
        pending_welcome = SMSAutomationDelivery.objects.create(
            user=self.user, rule=welcome, event_key="WELCOME:REGISTRATION:1",
            event="WELCOME", phone=self.user.phone, text="Welcome", scheduled_at=now,
        )
        pending_trial = SMSAutomationDelivery.objects.create(
            user=self.user, rule=trial, event_key="TRIAL:1:TRIAL_1",
            event="TRIAL", phone=self.user.phone, text="Trial", scheduled_at=now,
        )

        output = StringIO()
        call_command("activate_trial_journey", "--apply", "--confirm", stdout=output)
        summary = json.loads(output.getvalue())

        welcome.refresh_from_db()
        trial.refresh_from_db()
        pending_welcome.refresh_from_db()
        pending_trial.refresh_from_db()
        self.assertTrue(welcome.enabled)
        self.assertFalse(trial.enabled)
        self.assertEqual(pending_welcome.status, "PENDING")
        self.assertEqual(pending_trial.status, "SKIPPED")
        self.assertEqual(pending_trial.failure_code, "REPLACED_BY_TRIAL_JOURNEY")
        self.assertTrue(TrialJourneyActivation.objects.filter(pk=1).exists())
        self.assertEqual(summary["welcome_enabled_rules_to_keep"], 1)
        self.assertEqual(summary["welcome_pending_deliveries_to_keep"], 1)
