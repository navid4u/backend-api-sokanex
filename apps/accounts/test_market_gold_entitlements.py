from datetime import timedelta

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.signals.models import VIPSignalPost
from common.content_access import user_can_access_gold_content

from .models import TrialCampaign, TrialGrant, User, UserMarketGrant


@override_settings(MARKET_ACCESS_V2_ENABLED=True, CRM_ENABLED=False)
class MarketGoldEntitlementTests(APITestCase):
    def setUp(self):
        now = timezone.now()
        self.admin = User.objects.create_user(username="gold-v2-admin", role=User.Role.SUPER_ADMIN)
        self.user = User.objects.create_user(
            username="gold-v2-user", access_level=5,
            gold_trial_started_at=now, gold_trial_expires_at=now + timedelta(days=7),
        )
        self.crypto = VIPSignalPost.objects.create(channel="CRYPTO", text="Crypto post")
        self.forex = VIPSignalPost.objects.create(channel="FOREX", text="Forex post")

    def test_legacy_gold_does_not_grant_v2_gold_without_new_entitlement(self):
        self.client.force_authenticate(self.user)
        self.assertFalse(user_can_access_gold_content(self.user))
        self.assertEqual(self.client.get("/api/signals/").status_code, 403)
        self.assertEqual(
            self.client.post("/api/channels/ticket/", {"channel": "internal-analysis"}, format="json").status_code,
            403,
        )
        with override_settings(MARKET_ACCESS_V2_ENABLED=False):
            self.assertTrue(user_can_access_gold_content(self.user))
            self.assertEqual(self.client.get("/api/signals/").status_code, 200)

    def test_active_trial_grants_gold_and_both_signal_markets(self):
        campaign = TrialCampaign.objects.create(created_by=self.admin, status=TrialCampaign.Status.APPLIED)
        TrialGrant.objects.create(
            user=self.user, campaign=campaign,
            started_at=timezone.now() - timedelta(minutes=1),
            ends_at=timezone.now() + timedelta(days=7),
        )
        self.client.force_authenticate(self.user)
        self.assertTrue(user_can_access_gold_content(self.user))
        self.assertEqual(
            self.client.post("/api/channels/ticket/", {"channel": "internal-analysis"}, format="json").status_code,
            200,
        )
        for channel, post in (("crypto", self.crypto), ("forex", self.forex)):
            feed = self.client.get("/api/signals/", {"channel": channel})
            self.assertEqual(feed.status_code, 200)
            self.assertEqual(feed.data["count"], 1)
            self.assertEqual(self.client.get(f"/api/signals/{post.pk}/").status_code, 200)

    def test_three_markets_grant_gold_without_legacy_level_change(self):
        for market in User.MarketType.values:
            UserMarketGrant.objects.create(
                user=self.user, market=market,
                source=UserMarketGrant.Source.ADMIN, granted_by=self.admin,
            )
        self.assertTrue(user_can_access_gold_content(self.user))
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get("/api/signals/").status_code, 200)

    def test_superadmin_retains_gold_access(self):
        self.assertTrue(user_can_access_gold_content(self.admin))
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(f"/api/signals/{self.crypto.pk}/").status_code, 200)
