from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import override_settings
from rest_framework.test import APITestCase

from apps.assets.models import AssetCatalogItem, AssetCategory, AssetRiskLevel, AssetUnit, UserAssetHolding

from .invitations import attribute_new_user
from .market_trial import start_new_user_trial
from .models import InvitationLink, InvitationRegistration, TrialAutoStartSettingsAudit, TrialGrant, User


@override_settings(MARKET_ACCESS_V2_ENABLED=True, CRM_ENABLED=False)
class OctoberBackendExtensionTests(APITestCase):
    settings_url = "/api/accounts/admin/market-access/trial-settings/"
    links_url = "/api/accounts/admin/invitation-links/"

    def setUp(self):
        self.superadmin = User.objects.create_user(username="owner-oct", role=User.Role.SUPER_ADMIN)
        self.member = User.objects.create_user(username="member-oct")
        self.support = User.objects.create_user(username="support-oct", role=User.Role.SUPPORT)

    def test_trial_settings_persist_and_only_new_user_is_started_once(self):
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get(self.settings_url).status_code, 403)
        self.client.force_authenticate(self.superadmin)
        self.assertEqual(self.client.get(self.settings_url).data, {"auto_start_new_users": False})
        response = self.client.patch(self.settings_url, {"auto_start_new_users": True}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.client.get(self.settings_url).data["auto_start_new_users"])
        self.assertEqual(TrialAutoStartSettingsAudit.objects.count(), 1)
        self.assertFalse(TrialGrant.objects.filter(user=self.member).exists())
        new_user = User.objects.create_user(username="new-oct")
        first = start_new_user_trial(new_user)
        second = start_new_user_trial(new_user)
        self.assertIsNone(second)
        self.assertEqual(TrialGrant.objects.filter(user=new_user).count(), 1)
        self.assertEqual(first.ends_at - first.started_at, timedelta(days=7))
        self.assertIsNone(start_new_user_trial(self.support))

    def test_invitation_attribution_and_pagination_are_private(self):
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get(self.links_url).status_code, 403)
        self.client.force_authenticate(self.superadmin)
        response = self.client.post(self.links_url, {"name": "کمپین تست"}, format="json")
        self.assertEqual(response.status_code, 201)
        link = InvitationLink.objects.get(pk=response.data["id"])
        self.assertGreaterEqual(len(link.token), 32)
        self.assertTrue(response.data["registration_url"].endswith(link.token))
        attribute_new_user(user=self.member, token=link.token)
        attribute_new_user(user=self.member, token="invalid", fallback_link=link)
        self.assertEqual(InvitationRegistration.objects.filter(user=self.member).count(), 1)
        self.assertEqual(self.client.get(self.links_url).data["results"][0]["registrations_count"], 1)
        registrants = self.client.get(f"{self.links_url}{link.pk}/registrations/")
        self.assertEqual(registrants.status_code, 200)
        self.assertEqual(registrants.data["count"], 1)
        self.assertEqual(registrants.data["results"][0]["id"], self.member.pk)

    def test_credential_registration_attributes_invite_and_auto_starts_trial(self):
        self.client.force_authenticate(self.superadmin)
        self.client.patch(self.settings_url, {"auto_start_new_users": True}, format="json")
        link = self.client.post(self.links_url, {"name": "New users"}, format="json")
        token = InvitationLink.objects.get(pk=link.data["id"]).token
        self.client.force_authenticate(user=None)
        response = self.client.post("/api/accounts/register/", {
            "username": "invite-created-oct", "email": "invite-created-oct@example.org",
            "first_name": "New", "last_name": "Member", "password": "StrongPassword!123",
            "password_confirm": "StrongPassword!123", "invite_token": token,
        }, format="json")
        self.assertIn(response.status_code, (200, 201))
        user = User.objects.get(username="invite-created-oct")
        self.assertEqual(InvitationRegistration.objects.get(user=user).link.token, token)
        self.assertEqual(TrialGrant.objects.filter(user=user).count(), 1)
        self.client.force_authenticate(self.superadmin)
        self.assertEqual(self.client.get(self.links_url).data["results"][0]["registrations_count"], 1)

    @override_settings(
        PAYAMITO_ENABLED=True, PAYAMITO_USERNAME="test-user",
        PAYAMITO_API_KEY="test-key", PAYAMITO_FROM_NUMBER="5000",
    )
    def test_otp_registration_uses_invite_from_challenge_without_duplicate(self):
        self.client.force_authenticate(self.superadmin)
        self.client.patch(self.settings_url, {"auto_start_new_users": True}, format="json")
        link_id = self.client.post(self.links_url, {"name": "OTP audience"}, format="json").data["id"]
        link = InvitationLink.objects.get(pk=link_id)
        self.client.force_authenticate(user=None)
        with patch("apps.accounts.otp.secrets.randbelow", return_value=4839), patch(
            "apps.accounts.otp.PayamitoService.send_otp"
        ):
            requested = self.client.post("/api/accounts/auth/registration/request/", {
                "phone": "09120000099", "invite_token": link.token,
            }, format="json")
        self.assertEqual(requested.status_code, 200)
        verified = self.client.post("/api/accounts/auth/registration/verify/", {
            "phone": "09120000099", "code": "4839",
        }, format="json")
        self.assertEqual(verified.status_code, 200)
        user = User.objects.get(phone="09120000099")
        self.assertEqual(InvitationRegistration.objects.get(user=user).link_id, link.pk)
        self.assertEqual(TrialGrant.objects.filter(user=user).count(), 1)

    def test_asset_holdings_are_superadmin_only_and_paginated(self):
        category = AssetCategory.objects.create(code="test-oct", title_fa="آزمایش")
        for number in range(2):
            item = AssetCatalogItem.objects.create(
                code=f"asset-oct-{number}", category=category, name_fa=f"دارایی {number}",
                risk_level=AssetRiskLevel.LOW, unit=AssetUnit.GRAM,
            )
            UserAssetHolding.objects.create(
                user=self.member, asset=item, quantity=Decimal("1.25000000"), unit=AssetUnit.GRAM,
            )
        url = f"/api/accounts/admin/users/{self.member.pk}/asset-holdings/?page_size=1"
        self.client.force_authenticate(self.support)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_authenticate(self.superadmin)
        first = self.client.get(url)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data["count"], 2)
        self.assertEqual(len(first.data["results"]), 1)
        self.assertEqual(first.data["results"][0]["quantity"], "1.25000000")
        self.assertIsNotNone(first.data["next"])
        self.assertEqual(self.client.get(f"/api/accounts/admin/users/999999/asset-holdings/").status_code, 404)
