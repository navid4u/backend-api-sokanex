from datetime import timedelta

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.articles.models import Article
from apps.livestream.models import LiveEvent
from apps.videos.models import Video

from .content_section_access import user_can_access_content_section
from .models import (
    ContentSectionAccessAudit,
    ContentSectionAccessPolicy,
    TrialCampaign,
    TrialGrant,
    User,
    UserMarketGrant,
)


@override_settings(MARKET_ACCESS_V2_ENABLED=True, CRM_ENABLED=False)
class ContentSectionPolicyTests(APITestCase):
    policy_url = "/api/accounts/admin/market-access/content-policy/"

    def setUp(self):
        self.admin = User.objects.create_user(username="section-super", role=User.Role.SUPER_ADMIN)
        self.user = User.objects.create_user(username="section-user", access_level=1)
        now = timezone.now()
        self.article = Article.objects.create(
            title="Open article", content="Article content", author=self.admin,
            status=Article.Status.PUBLISHED, published_at=now,
            allowed_level_1=False, allowed_level_2=False, allowed_level_3=False,
            allowed_level_4=False, allowed_level_5=False,
        )
        self.video = Video.objects.create(
            title="Open video", author=self.admin,
            status=Video.Status.PUBLISHED, published_at=now,
            allowed_level_1=False, allowed_level_2=False, allowed_level_3=False,
            allowed_level_4=False, allowed_level_5=False,
        )
        self.live = LiveEvent.objects.create(
            title="Open live", created_by=self.admin,
            starts_at=now + timedelta(hours=1), status=LiveEvent.Status.UPCOMING,
            allowed_level_1=False, allowed_level_2=False, allowed_level_3=False,
            allowed_level_4=False, allowed_level_5=False,
        )

    def test_default_policy_opens_all_three_sections_despite_legacy_item_flags(self):
        self.client.force_authenticate(self.user)
        for url in (
            f"/api/articles/{self.article.slug}/",
            f"/api/videos/{self.video.slug}/",
            f"/api/livestream/{self.live.slug}/",
        ):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertFalse(ContentSectionAccessPolicy.objects.exists())

    def test_admin_policy_disables_only_selected_section_and_tier(self):
        self.client.force_authenticate(self.admin)
        initial = self.client.get(self.policy_url)
        self.assertEqual(initial.status_code, 200)
        self.assertEqual(len(initial.data), 3)
        self.assertEqual(
            initial.data[0]["allowed_tiers"], ["LEVEL_1", "BASIC", "PRO", "GOLD"],
        )
        changed = self.client.patch(
            self.policy_url,
            {"section": "ARTICLES", "allowed_tiers": ["BASIC", "PRO", "GOLD"]},
            format="json",
        )
        self.assertEqual(changed.status_code, 200, changed.data)
        self.assertEqual(ContentSectionAccessAudit.objects.count(), 1)
        self.assertEqual(ContentSectionAccessAudit.objects.first().actor, self.admin)
        self.article.refresh_from_db()
        self.assertFalse(self.article.allowed_level_1)
        self.client.force_authenticate(self.user)
        articles = self.client.get("/api/articles/")
        videos = self.client.get("/api/videos/")
        lives = self.client.get("/api/livestream/")
        self.assertEqual(articles.status_code, 200)
        self.assertEqual(videos.status_code, 200)
        self.assertEqual(lives.status_code, 200)
        self.assertEqual(articles.data["count"], 0)
        self.assertEqual(videos.data["count"], 1)
        self.assertEqual(lives.data["count"], 1)
        self.assertEqual(self.client.get(f"/api/articles/{self.article.slug}/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/videos/{self.video.slug}/").status_code, 200)
        self.assertEqual(self.client.get(f"/api/livestream/{self.live.slug}/").status_code, 200)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(f"/api/articles/{self.article.slug}/").status_code, 200)

    def test_tier_grants_and_trial_overlay_follow_global_switches(self):
        UserMarketGrant.objects.create(
            user=self.user, market=User.MarketType.CRYPTO,
            source=UserMarketGrant.Source.ADMIN, granted_by=self.admin,
        )
        ContentSectionAccessPolicy.objects.create(section="VIDEOS", allowed_tiers=["LEVEL_1", "GOLD"])
        self.assertFalse(user_can_access_content_section(self.user, "VIDEOS"))
        campaign = TrialCampaign.objects.create(created_by=self.admin, status=TrialCampaign.Status.APPLIED)
        TrialGrant.objects.create(
            user=self.user, campaign=campaign,
            started_at=timezone.now() - timedelta(minutes=1),
            ends_at=timezone.now() + timedelta(days=7),
        )
        self.assertTrue(user_can_access_content_section(self.user, "VIDEOS"))
        ContentSectionAccessPolicy.objects.filter(section="VIDEOS").update(allowed_tiers=["BASIC"])
        self.assertFalse(user_can_access_content_section(self.user, "VIDEOS"))

    def test_permission_validation_and_noop_audit(self):
        self.assertEqual(self.client.get(self.policy_url).status_code, 401)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get(self.policy_url).status_code, 403)
        self.assertEqual(self.client.patch(self.policy_url, {"section": "ARTICLES", "allowed_tiers": []}, format="json").status_code, 403)
        self.client.force_authenticate(self.admin)
        for payload in (
            {"section": "ARTICLES", "allowed_tiers": ["BASIC", "BASIC"]},
            {"section": "ARTICLES", "allowed_tiers": ["PREMIUM"]},
            {"section": "ARTICLES", "allowed_tiers": [], "updated_by": self.user.pk},
        ):
            self.assertEqual(self.client.patch(self.policy_url, payload, format="json").status_code, 400)
        self.assertFalse(ContentSectionAccessPolicy.objects.exists())
        valid = {"section": "ARTICLES", "allowed_tiers": ["LEVEL_1", "BASIC", "PRO", "GOLD"]}
        self.assertEqual(self.client.patch(self.policy_url, valid, format="json").status_code, 200)
        self.assertFalse(ContentSectionAccessAudit.objects.exists())

    def test_flag_off_preserves_legacy_item_visibility_and_blocks_policy_api(self):
        self.client.force_authenticate(self.user)
        with override_settings(MARKET_ACCESS_V2_ENABLED=False):
            self.assertEqual(self.client.get(f"/api/articles/{self.article.slug}/").status_code, 404)
            self.assertEqual(self.client.get(f"/api/videos/{self.video.slug}/").status_code, 404)
            self.assertEqual(self.client.get(f"/api/livestream/{self.live.slug}/").status_code, 404)
            self.client.force_authenticate(self.admin)
            self.assertEqual(self.client.get(self.policy_url).status_code, 403)

    def test_live_socket_permission_uses_same_global_policy(self):
        self.assertTrue(user_can_access_content_section(
            self.user, "LIVESTREAMS", legacy_allowed_levels=[],
        ))
        ContentSectionAccessPolicy.objects.create(section="LIVESTREAMS", allowed_tiers=["BASIC", "PRO", "GOLD"])
        self.assertFalse(user_can_access_content_section(
            self.user, "LIVESTREAMS", legacy_allowed_levels=[1],
        ))
        with override_settings(MARKET_ACCESS_V2_ENABLED=False):
            self.assertTrue(user_can_access_content_section(
                self.user, "LIVESTREAMS", legacy_allowed_levels=[1],
            ))
