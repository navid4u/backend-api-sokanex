"""Cross-endpoint tests for the V2 market-scoped VIP contract."""

from datetime import timedelta

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.content_channels.models import Channel, ChannelPost
from apps.signals.models import VIPSignalPost

from .models import User, UserMarketGrant


@override_settings(MARKET_ACCESS_V2_ENABLED=True, CRM_ENABLED=False)
class MarketScopedVIPTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="vip-admin", role=User.Role.SUPER_ADMIN)
        self.support = User.objects.create_user(username="vip-support", role=User.Role.SUPPORT)
        self.spoof = User.objects.create_user(username="support")
        self.user = User.objects.create_user(
            username="vip-normal", access_level=5, market_type="forex",
            gold_trial_started_at=timezone.now() - timedelta(days=8),
            gold_trial_expires_at=timezone.now() - timedelta(days=1),
        )
        self.crypto = VIPSignalPost.objects.create(channel="CRYPTO", text="crypto private")
        self.forex = VIPSignalPost.objects.create(channel="FOREX", text="forex private")
        channel, _ = Channel.objects.get_or_create(slug="internal-analysis", defaults={"name": "Internal"})
        self.analysis = ChannelPost.objects.create(
            channel=channel, author=self.admin, title="Domestic private",
            body="Analysis private", scope=ChannelPost.Scope.GOLD,
            status=ChannelPost.Status.PUBLISHED, published_at=timezone.now(),
        )
        self.forex_analysis = ChannelPost.objects.create(
            channel=channel, author=self.admin, title="Forex private",
            body="Forex analysis", scope=ChannelPost.Scope.FOREX,
            status=ChannelPost.Status.PUBLISHED, published_at=timezone.now(),
        )

    def grant(self, *markets):
        for market in markets:
            UserMarketGrant.objects.create(user=self.user, market=market, source=UserMarketGrant.Source.ADMIN)

    def test_official_roles_bypass_content_locks_but_username_does_not(self):
        for actor in (self.admin, self.support):
            with self.subTest(actor=actor.username):
                self.client.force_authenticate(actor)
                self.assertEqual(self.client.get("/api/signals/?channel=CRYPTO").status_code, 200)
                self.assertEqual(self.client.get("/api/signals/?channel=FOREX").status_code, 200)
                self.assertEqual(self.client.get("/api/channels/internal-analysis/").status_code, 200)
                self.assertEqual(self.client.get("/api/academy/courses/").status_code, 200)
                self.assertEqual(self.client.post("/api/assistant/chat/", {"messages": []}, format="json").status_code, 400)
                profile = self.client.get("/api/accounts/profile/")
                self.assertEqual(profile.data["special_role"], actor.role)
                self.assertEqual(profile.data["role"], actor.role)
                dashboard = self.client.get("/api/dashboard/").data["data"]
                self.assertEqual(dashboard["special_role"], actor.role)
                self.assertEqual(dashboard["user"]["special_role"], actor.role)
                if actor == self.support:
                    self.assertTrue(dashboard["capabilities"]["can_manage_market_access"])
                    self.assertFalse(dashboard["capabilities"]["can_manage_sms_automation"])
        self.client.force_authenticate(self.spoof)
        self.assertEqual(self.client.get("/api/signals/?channel=CRYPTO").status_code, 403)
        self.assertEqual(self.client.get("/api/channels/internal-analysis/").status_code, 403)
        self.assertEqual(self.client.post("/api/assistant/chat/", {"messages": []}, format="json").status_code, 403)

    def test_basic_and_pro_only_see_granted_markets(self):
        self.grant("crypto")
        self.client.force_authenticate(self.user)
        profile = self.client.get("/api/accounts/profile/").data["market_access_v2"]
        self.assertEqual(profile["membership_tier"], "BASIC")
        self.assertFalse(profile["has_gold_features"])
        self.assertEqual(self.client.get("/api/signals/?channel=CRYPTO").status_code, 200)
        self.assertEqual(self.client.get(f"/api/signals/{self.crypto.pk}/").status_code, 200)
        self.assertEqual(self.client.get("/api/signals/?channel=FOREX").status_code, 403)
        self.assertEqual(self.client.get(f"/api/signals/{self.forex.pk}/").status_code, 403)
        self.assertEqual(self.client.get("/api/channels/internal-analysis/").status_code, 403)
        previews = self.client.get("/api/dashboard/").data["data"]["vip_signal_previews"]
        self.assertEqual({p["channel"] for p in previews if p["can_view"]}, {"CRYPTO"})
        self.grant("internal")
        profile = self.client.get("/api/accounts/profile/").data["market_access_v2"]
        self.assertEqual(profile["membership_tier"], "PRO")
        self.assertEqual(self.client.get("/api/channels/internal-analysis/").status_code, 200)
        self.assertEqual(self.client.get("/api/signals/?channel=FOREX").status_code, 403)
        internal = self.client.get("/api/channels/internal-analysis/").data["results"]
        self.assertEqual([item["id"] for item in internal], [self.analysis.pk])
        self.assertEqual(self.client.get("/api/channels/internal-analysis/?scope=FOREX").status_code, 403)

    def test_revoke_immediately_closes_feed_and_preview(self):
        self.grant("crypto")
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get("/api/signals/?channel=CRYPTO").status_code, 200)
        self.client.force_authenticate(self.admin)
        changed = self.client.patch(
            f"/api/accounts/admin/market-access/users/{self.user.pk}/",
            {"approved_markets": []}, format="json",
        )
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.data["access"]["membership_tier"], "LEVEL_1")
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get("/api/signals/?channel=CRYPTO").status_code, 403)
        dashboard = self.client.get("/api/dashboard/")
        self.assertEqual(dashboard.data["data"]["recent_signals"], [])
        self.assertFalse(dashboard.data["data"]["vip_signal_previews"][0]["can_view"])
        self.assertIn("no-store", dashboard["Cache-Control"])

    def test_preferences_do_not_grant_content(self):
        self.client.force_authenticate(self.user)
        selected = self.client.put(
            "/api/accounts/profile/market-preferences/",
            {"selected_markets": ["crypto"]}, format="json",
        )
        self.assertEqual(selected.status_code, 200)
        self.assertEqual(selected.data["approved_markets"], [])
        self.assertEqual(self.client.get("/api/signals/?channel=CRYPTO").status_code, 403)

    def test_v2_disabled_keeps_legacy_gold_gate(self):
        self.client.force_authenticate(self.user)
        with override_settings(MARKET_ACCESS_V2_ENABLED=False):
            self.assertEqual(self.client.get("/api/signals/?channel=CRYPTO").status_code, 403)
