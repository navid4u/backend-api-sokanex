from datetime import timedelta
from io import StringIO
from importlib import import_module
import json
from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.db import connection
from django.apps import apps
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from .models import (
    TrialCampaign, TrialGrant, User, UserAccessAudit, UserAccessProfile,
    UserMarketGrant, UserMarketPreference,
)
from .market_access import resolve_market_access
from .views import RegisterView


@override_settings(MARKET_ACCESS_V2_ENABLED=True, CRM_ENABLED=False)
class RegistrationMarketJourneyTests(APITestCase):
    def setUp(self):
        throttle_patch = patch.object(RegisterView, "throttle_classes", [])
        throttle_patch.start()
        self.addCleanup(throttle_patch.stop)

    def test_email_registration_without_phone_is_level_one_and_returns_tokens(self):
        response = self.client.post("/api/accounts/register/", {
            "username": "new.email.user", "email": "  New.User@Example.COM  ",
            "password": "StrongPass123!", "password_confirm": "StrongPass123!",
            "first_name": "New", "last_name": "User",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        user = User.objects.get(username="new.email.user")
        self.assertEqual(user.email, "new.user@example.com")
        self.assertIsNone(user.phone)
        self.assertEqual(response.data["tokens"]["access"], response.data["access"])
        self.assertEqual(response.data["tokens"]["refresh"], response.data["refresh"])
        self.assertNotIn("password_confirm", response.data)
        self.assertEqual(response.data["user"]["market_access_v2"]["membership_tier"], "LEVEL_1")
        self.assertEqual(response.data["user"]["market_access_v2"]["effective_markets"], [])
        self.assertFalse(TrialGrant.objects.filter(user=user).exists())

    def test_email_uniqueness_validation_and_database_constraint(self):
        User.objects.create_user(username="existing", email="existing@example.com")
        payload = {
            "username": "second", "email": "EXISTING@EXAMPLE.COM",
            "password": "StrongPass123!", "first_name": "New", "last_name": "User",
        }
        response = self.client.post("/api/accounts/register/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.data["errors"])
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(username="third", email="EXISTING@example.com")

    def test_optional_confirmation_and_invalid_inputs(self):
        base = {
            "username": "another", "email": "another@example.com",
            "password": "StrongPass123!", "first_name": "New", "last_name": "User",
        }
        self.assertEqual(self.client.post("/api/accounts/register/", base, format="json").status_code, 201)
        for changed, key in (
            ({"username": "another", "email": "different@example.com"}, "username"),
            ({"username": "third", "email": "third@example.com", "password_confirm": "wrong"}, "password_confirm"),
            ({"username": "fourth", "email": "fourth@example.com", "password": "123"}, "password"),
        ):
            with self.subTest(changed=changed):
                result = self.client.post("/api/accounts/register/", {**base, **changed}, format="json")
                self.assertEqual(result.status_code, 400)
                self.assertIn(key, result.data["errors"])

    def test_market_confirmation_survives_login_and_trial_expiry(self):
        user = User.objects.create_user(username="market-user", access_level=5)
        self.client.force_authenticate(user)
        response = self.client.put(
            "/api/accounts/profile/market-preferences/",
            {"selected_markets": ["forex", "crypto"]}, format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["membership_tier"], "LEVEL_1")
        self.assertTrue(response.data["market_selection_confirmed"])
        self.client.force_authenticate(user=None)
        self.client.force_authenticate(User.objects.get(pk=user.pk))
        campaign = TrialCampaign.objects.create()
        now = timezone.now()
        TrialGrant.objects.create(user=user, campaign=campaign, started_at=now-timedelta(days=8), ends_at=now-timedelta(days=1))
        for path in (
            "/api/accounts/profile/market-preferences/",
            "/api/accounts/profile/details/",
            "/api/dashboard/",
        ):
            result = self.client.get(path)
            self.assertEqual(result.status_code, 200)
            state = (
                result.data if "market-preferences" in path
                else result.data["data"]["market_access_v2"] if path == "/api/dashboard/"
                else result.data["market_access_v2"]
            )
            self.assertTrue(state["market_selection_confirmed"])
            self.assertEqual(state["membership_tier"], "LEVEL_1")
            self.assertEqual(state["effective_markets"], [])
        self.assertEqual(UserMarketPreference.objects.filter(user=user).count(), 2)
        self.assertEqual(UserAccessProfile.objects.get(user=user).market_selection_confirmed_at is not None, True)

    def test_backfill_uses_explicit_preferences_not_legacy_market_type(self):
        selected = User.objects.create_user(username="selected-before-flag")
        defaulted = User.objects.create_user(username="legacy-market-only", market_type="forex")
        UserMarketPreference.objects.create(user=selected, market="crypto")
        migration = import_module(
            "apps.accounts.migrations.0025_registration_email_market_confirmation_trial_revoke"
        )
        migration.backfill_explicit_market_selection(apps, SimpleNamespace(connection=connection))
        self.assertTrue(UserAccessProfile.objects.get(user=selected).market_selection_confirmed_at)
        self.assertFalse(UserAccessProfile.objects.filter(user=defaulted).exists())

    def test_legacy_level_five_jwt_claim_does_not_grant_v2_access(self):
        user = User.objects.create_user(username="old-level-five", access_level=5)
        token = RefreshToken.for_user(user).access_token
        token["access_level"] = 5
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        result = self.client.get("/api/accounts/profile/market-preferences/")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["membership_tier"], "LEVEL_1")
        self.assertEqual(result.data["approved_markets"], [])
        self.assertEqual(result.data["effective_markets"], [])

    def test_registration_rejects_client_role_and_level(self):
        base = {
            "username": "no-escalation", "email": "no-escalation@example.com",
            "password": "StrongPass123!", "first_name": "New", "last_name": "User",
        }
        for extra in ({"role": "SUPER_ADMIN"}, {"access_level": 5}):
            response = self.client.post("/api/accounts/register/", {**base, **extra}, format="json")
            self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(username="no-escalation").exists())

    def test_cohort_restart_is_preview_only_then_audited_apply(self):
        normal = User.objects.create_user(username="cohort", access_level=5)
        superadmin = User.objects.create_superuser(username="superadmin", email="superadmin@example.com", password="StrongPass123!")
        support = User.objects.create_user(username="journey-support", role=User.Role.SUPPORT)
        UserMarketGrant.objects.create(user=normal, market="crypto", source="ADMIN")
        UserMarketGrant.objects.create(user=support, market="forex", source="ADMIN")
        UserAccessProfile.objects.create(user=normal, is_elite=True)
        campaign = TrialCampaign.objects.create(created_by=superadmin)
        TrialGrant.objects.create(user=normal, campaign=campaign, started_at=timezone.now(), ends_at=timezone.now()+timedelta(days=7))
        output = StringIO()
        call_command("restart_market_access_v2_cohort", stdout=output)
        report = json.loads(output.getvalue())
        self.assertEqual(report["mode"], "dry_run")
        self.assertEqual(report["active_v2_grants_to_revoke"], 1)
        self.assertEqual(report["active_v2_trials_to_revoke"], 1)
        self.assertFalse(UserAccessAudit.objects.exists())
        output = StringIO()
        call_command("restart_market_access_v2_cohort", apply=True, confirm_v2_trials_remain_used=True, stdout=output)
        self.assertEqual(json.loads(output.getvalue())["users_to_audit"], 1)
        self.assertTrue(UserMarketGrant.objects.get(user=normal).revoked_at)
        self.assertTrue(TrialGrant.objects.get(user=normal).revoked_at)
        self.assertFalse(UserAccessProfile.objects.get(user=normal).is_elite)
        self.assertEqual(User.objects.get(pk=normal.pk).access_level, 5)  # legacy history retained
        self.assertIsNone(UserMarketGrant.objects.get(user=support).revoked_at)
        self.assertEqual(UserAccessAudit.objects.filter(subject_user_id=normal.pk).count(), 1)
        normal.refresh_from_db()
        self.assertEqual(resolve_market_access(normal).membership_tier, "LEVEL_1")
        self.assertFalse(resolve_market_access(normal).trial_active)
        again = StringIO()
        call_command("restart_market_access_v2_cohort", apply=True, confirm_v2_trials_remain_used=True, stdout=again)
        self.assertEqual(json.loads(again.getvalue())["users_to_audit"], 0)
        self.assertEqual(UserAccessAudit.objects.filter(subject_user_id=normal.pk).count(), 1)

    def test_admin_can_still_revoke_all_approved_markets(self):
        admin = User.objects.create_user(username="revocation-admin", role=User.Role.SUPER_ADMIN)
        target = User.objects.create_user(username="revocation-target")
        UserMarketGrant.objects.create(user=target, market="crypto", source="ADMIN")
        self.client.force_authenticate(admin)
        result = self.client.patch(
            f"/api/accounts/admin/market-access/users/{target.pk}/",
            {"approved_markets": []}, format="json",
        )
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data["access"]["membership_tier"], "LEVEL_1")
        self.assertEqual(result.data["access"]["approved_markets"], [])
        self.assertTrue(UserMarketGrant.objects.get(user=target).revoked_at)
