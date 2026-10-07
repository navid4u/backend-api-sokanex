from django.test import override_settings
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APITestCase
from unittest.mock import patch

from .market_access_admin import update_user_market_access
from .models import User, UserAccessAudit, UserMarketGrant, UserMarketPreference


@override_settings(MARKET_ACCESS_V2_ENABLED=True, CRM_ENABLED=False)
class MarketAccessAdminAPITests(APITestCase):
    list_url = "/api/accounts/admin/market-access/users/"

    def setUp(self):
        self.admin = User.objects.create_user(username="v2-super", role=User.Role.SUPER_ADMIN)
        self.support = User.objects.create_user(username="v2-support", role=User.Role.SUPPORT)
        self.user = User.objects.create_user(username="v2-user", phone="09123456789")

    def detail_url(self, user=None):
        return f"{self.list_url}{(user or self.user).pk}/"

    def test_feature_flag_blocks_reads_and_writes(self):
        self.client.force_authenticate(self.admin)
        with override_settings(MARKET_ACCESS_V2_ENABLED=False):
            self.assertEqual(self.client.get(self.list_url).status_code, 403)
            self.assertEqual(
                self.client.patch(self.detail_url(), {"approved_markets": ["crypto"]}, format="json").status_code,
                403,
            )
        self.assertFalse(UserMarketGrant.objects.filter(user=self.user).exists())

    def test_permission_anonymous_and_regular_user_denied_support_allowed(self):
        self.assertEqual(self.client.get(self.list_url).status_code, 401)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get(self.list_url).status_code, 403)
        self.assertEqual(
            self.client.patch(self.detail_url(), {"approved_markets": ["crypto"]}, format="json").status_code,
            403,
        )
        self.client.force_authenticate(self.support)
        self.assertEqual(self.client.get(self.list_url).status_code, 200)

    def test_profile_capability_exposes_support_management_only_when_enabled(self):
        self.client.force_authenticate(self.support)
        enabled = self.client.get("/api/accounts/profile/")
        self.assertEqual(enabled.status_code, 200)
        self.assertTrue(enabled.data["capabilities"]["can_manage_market_access"])
        with override_settings(MARKET_ACCESS_V2_ENABLED=False):
            disabled = self.client.get("/api/accounts/profile/")
        self.assertEqual(disabled.status_code, 200)
        self.assertFalse(disabled.data["capabilities"]["can_manage_market_access"])

    def test_admin_list_is_paginated_and_searchable(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(self.list_url, {"search": "09123456789", "page_size": 10})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["id"], self.user.pk)

    def test_read_distinguishes_preferences_from_approved_grants(self):
        UserMarketPreference.objects.create(user=self.user, market="crypto")
        self.client.force_authenticate(self.support)
        response = self.client.get(self.detail_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["access"]["selected_markets"], ["crypto"])
        self.assertEqual(response.data["access"]["approved_markets"], [])
        self.assertEqual(response.data["access"]["membership_tier"], "LEVEL_1")
        self.assertEqual(response.data["legacy_access_level"], 1)

    def test_atomic_patch_derives_tier_and_writes_audit_without_changing_legacy(self):
        self.client.force_authenticate(self.support)
        response = self.client.patch(
            self.detail_url(),
            {"approved_markets": ["crypto", "forex"], "is_elite": True},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["access"]["membership_tier"], "PRO")
        self.assertEqual(response.data["access"]["approved_markets"], ["crypto", "forex"])
        self.assertTrue(response.data["access"]["is_elite"])
        self.user.refresh_from_db()
        self.assertEqual(self.user.access_level, 1)
        audit = UserAccessAudit.objects.filter(subject_user_id=self.user.pk)
        self.assertEqual(audit.count(), 3)
        self.assertEqual(audit.order_by().values_list("operation_id", flat=True).distinct().count(), 1)
        self.assertTrue(all(entry.actor_id == self.support.pk for entry in audit))

        replay = self.client.patch(
            self.detail_url(),
            {"approved_markets": ["crypto", "forex"], "is_elite": True},
            format="json",
        )
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(audit.count(), 3)

    def test_revocation_preserves_history_and_updates_tier(self):
        self.client.force_authenticate(self.admin)
        self.client.patch(self.detail_url(), {"approved_markets": ["crypto", "forex"]}, format="json")
        response = self.client.patch(self.detail_url(), {"approved_markets": []}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["access"]["membership_tier"], "LEVEL_1")
        self.assertEqual(UserMarketGrant.objects.filter(user=self.user).count(), 2)
        self.assertEqual(UserMarketGrant.objects.filter(user=self.user, revoked_at__isnull=True).count(), 0)

    def test_invalid_payload_has_no_partial_writes(self):
        self.client.force_authenticate(self.admin)
        for payload in (
            {},
            {"approved_markets": ["crypto", "crypto"]},
            {"approved_markets": ["invalid"]},
            {"role": "SUPER_ADMIN"},
            {"approved_markets": ["crypto"], "access_level": 5},
        ):
            with self.subTest(payload=payload):
                response = self.client.patch(self.detail_url(), payload, format="json")
                self.assertEqual(response.status_code, 400)
        self.assertFalse(UserMarketGrant.objects.filter(user=self.user).exists())
        self.assertFalse(UserAccessAudit.objects.filter(subject_user_id=self.user.pk).exists())

    def test_cannot_edit_self_or_special_role_and_missing_user_is_404(self):
        self.client.force_authenticate(self.admin)
        payload = {"approved_markets": ["crypto"]}
        self.assertEqual(self.client.patch(self.detail_url(self.admin), payload, format="json").status_code, 403)
        self.assertEqual(self.client.patch(self.detail_url(self.support), payload, format="json").status_code, 403)
        self.assertEqual(self.client.get(f"{self.list_url}99999999/").status_code, 404)
        self.assertEqual(self.client.patch(f"{self.list_url}99999999/", payload, format="json").status_code, 404)

    def test_changing_one_user_does_not_change_another(self):
        another = User.objects.create_user(username="v2-other")
        self.client.force_authenticate(self.admin)
        self.client.patch(self.detail_url(), {"approved_markets": ["internal"]}, format="json")
        other = self.client.get(self.detail_url(another))
        self.assertEqual(other.status_code, 200)
        self.assertEqual(other.data["access"]["approved_markets"], [])
        self.assertFalse(UserAccessAudit.objects.filter(subject_user_id=another.pk).exists())

    def test_audit_failure_rolls_back_grant(self):
        with patch.object(UserAccessAudit.objects, "create", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                update_user_market_access(
                    actor=self.admin,
                    user_id=self.user.pk,
                    approved_markets=["crypto"],
                )
        self.assertFalse(UserMarketGrant.objects.filter(user=self.user).exists())

    def test_domain_service_rejects_unprivileged_actor(self):
        with self.assertRaises(PermissionDenied):
            update_user_market_access(
                actor=self.user,
                user_id=self.support.pk,
                approved_markets=["crypto"],
            )
