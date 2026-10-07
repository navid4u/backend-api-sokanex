from django.test import override_settings
from rest_framework.test import APITestCase

from .models import User, UserAccessAudit, UserAccessProfile, UserMarketGrant, UserMarketPreference


@override_settings(MARKET_ACCESS_V2_ENABLED=True, CRM_ENABLED=False)
class MyMarketPreferencesV2Tests(APITestCase):
    url = "/api/accounts/profile/market-preferences/"

    def setUp(self):
        self.user = User.objects.create_user(username="preferences-v2-user")
        self.support = User.objects.create_user(username="preferences-v2-support", role=User.Role.SUPPORT)
        self.client.force_authenticate(self.user)

    def test_selection_is_confirmed_once_but_never_grants_access(self):
        initial = self.client.get(self.url)
        self.assertEqual(initial.status_code, 200)
        self.assertFalse(initial.data["market_selection_confirmed"])
        response = self.client.put(
            self.url, {"selected_markets": ["crypto", "forex"]}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["selected_markets"], ["crypto", "forex"])
        self.assertEqual(response.data["approved_markets"], [])
        self.assertEqual(response.data["membership_tier"], "LEVEL_1")
        self.assertTrue(response.data["market_selection_confirmed"])
        self.assertFalse(UserMarketGrant.objects.filter(user=self.user).exists())
        profile = UserAccessProfile.objects.get(user=self.user)
        confirmed_at = profile.market_selection_confirmed_at
        self.assertEqual(UserAccessAudit.objects.filter(subject_user_id=self.user.pk).count(), 1)

        replay = self.client.put(
            self.url, {"selected_markets": ["forex", "crypto"]}, format="json"
        )
        self.assertEqual(replay.status_code, 200)
        profile.refresh_from_db()
        self.assertEqual(profile.market_selection_confirmed_at, confirmed_at)
        self.assertEqual(UserAccessAudit.objects.filter(subject_user_id=self.user.pk).count(), 1)

    def test_edit_and_empty_selection_preserve_access_separation(self):
        self.client.put(self.url, {"selected_markets": ["internal"]}, format="json")
        edited = self.client.put(self.url, {"selected_markets": []}, format="json")
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(edited.data["selected_markets"], [])
        self.assertTrue(edited.data["market_selection_confirmed"])
        self.assertFalse(UserMarketPreference.objects.filter(user=self.user).exists())
        self.assertEqual(UserAccessAudit.objects.filter(subject_user_id=self.user.pk).count(), 2)

    def test_invalid_input_is_400_and_cannot_escalate_level_or_role(self):
        for payload in (
            {"selected_markets": ["crypto", "crypto"]},
            {"selected_markets": ["unknown"]},
            {"selected_markets": ["crypto"], "approved_markets": ["crypto"]},
            {"selected_markets": ["crypto"], "access_level": 5},
            {"selected_markets": ["crypto"], "user_id": self.support.pk},
        ):
            with self.subTest(payload=payload):
                self.assertEqual(self.client.put(self.url, payload, format="json").status_code, 400)
        self.assertFalse(UserMarketPreference.objects.filter(user=self.user).exists())
        self.assertFalse(UserAccessAudit.objects.filter(subject_user_id=self.user.pk).exists())

    def test_flag_off_and_anonymous_are_blocked(self):
        with override_settings(MARKET_ACCESS_V2_ENABLED=False):
            self.assertEqual(self.client.get(self.url).status_code, 403)
            self.assertEqual(
                self.client.put(self.url, {"selected_markets": ["crypto"]}, format="json").status_code,
                403,
            )
            profile = self.client.get("/api/accounts/profile/")
            self.assertEqual(profile.status_code, 200)
            self.assertEqual(profile.data["market_access_v2"], {"enabled": False})
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_support_is_exempt_from_selection(self):
        self.client.force_authenticate(self.support)
        state = self.client.get(self.url)
        self.assertEqual(state.status_code, 200)
        self.assertEqual(state.data["special_role"], "SUPPORT")
        self.assertEqual(
            self.client.put(self.url, {"selected_markets": ["crypto"]}, format="json").status_code,
            403,
        )

    def test_profile_exposes_same_state_as_selection_endpoint(self):
        self.client.put(self.url, {"selected_markets": ["internal", "crypto"]}, format="json")
        state = self.client.get(self.url).data
        profile = self.client.get("/api/accounts/profile/")
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.data["market_access_v2"]["selected_markets"], state["selected_markets"])
        self.assertEqual(profile.data["market_access_v2"]["approved_markets"], [])
