"""The large trial cohort must lose content, not its selected markets."""

from datetime import timedelta
from inspect import unwrap

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.academy.models import Course, CourseSession
from apps.content_channels.models import Channel, ChannelPost
from apps.content_channels.consumers import ContentChannelConsumer
from apps.livestream.consumers import LivestreamConsumer
from apps.livestream.models import LiveEvent
from apps.notifications.models import Notification, NotificationSMSDelivery
from apps.signals.models import VIPSignalPost

from .models import MarketAccessRequest, TrialCampaign, TrialGrant, User


@override_settings(MARKET_ACCESS_V2_ENABLED=True, CRM_ENABLED=False)
class TrialExpiryContentGateTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="expiry-admin", role=User.Role.SUPER_ADMIN)
        self.user = User.objects.create_user(username="expiry-user", access_level=5)
        self.course = Course.objects.create(
            title="Crypto lessons", market="crypto", instructor=self.admin,
            status=Course.Status.PUBLISHED,
        )
        self.session = CourseSession.objects.create(course=self.course, title="First lesson", order=1)
        self.signal = VIPSignalPost.objects.create(channel="CRYPTO", text="Private signal")
        channel, _ = Channel.objects.get_or_create(
            slug="internal-analysis", defaults={"name": "Internal analysis"},
        )
        self.analysis = ChannelPost.objects.create(
            channel=channel, author=self.admin, title="Private opportunity",
            body="Private opportunity body", scope=ChannelPost.Scope.GOLD,
            status=ChannelPost.Status.PUBLISHED, published_at=timezone.now(),
        )
        self.live = LiveEvent.objects.create(
            title="Trial live", created_by=self.admin, is_active=True,
            status=LiveEvent.Status.ACTIVE,
            starts_at=timezone.now() - timedelta(minutes=5),
            ends_at=timezone.now() + timedelta(hours=1),
            stream_url="https://example.com/private-live",
        )
        campaign = TrialCampaign.objects.create(created_by=self.admin, status=TrialCampaign.Status.APPLIED)
        self.grant = TrialGrant.objects.create(
            user=self.user, campaign=campaign, started_at=timezone.now() - timedelta(days=1),
            ends_at=timezone.now() + timedelta(days=6),
        )
        self.client.force_authenticate(self.user)

    def dashboard(self):
        response = self.client.get("/api/dashboard/")
        self.assertEqual(response.status_code, 200)
        return response.data["data"]

    def expire_trial(self):
        TrialGrant.objects.filter(pk=self.grant.pk).update(
            started_at=timezone.now() - timedelta(days=8),
            ends_at=timezone.now() - timedelta(seconds=1),
        )

    def test_trial_expiry_closes_four_sections_and_approval_reopens_chosen_market(self):
        selected = self.client.put(
            "/api/accounts/profile/market-preferences/",
            {"selected_markets": ["crypto"]}, format="json",
        )
        self.assertEqual(selected.status_code, 200)
        self.assertTrue(self.dashboard()["content_access"]["livestream"])
        self.assertEqual(self.client.get(f"/api/academy/courses/{self.course.slug}/").status_code, 200)
        self.assertEqual(self.client.get("/api/signals/?channel=CRYPTO").status_code, 200)
        self.assertEqual(self.client.get("/api/channels/internal-analysis/").status_code, 200)
        self.assertEqual(self.client.get(f"/api/livestream/{self.live.slug}/").status_code, 200)

        self.expire_trial()
        dashboard = self.dashboard()
        self.assertEqual(dashboard["market_access_v2"]["trial_status"], "EXPIRED")
        self.assertEqual(dashboard["market_access_v2"]["effective_markets"], [])
        self.assertEqual(dashboard["content_access"], {
            "signals": {"crypto": False, "forex": False},
            "academy_markets": [], "livestream": False,
            "internal_opportunities": False,
        })
        self.assertEqual(dashboard["stats"]["signals"], 0)
        self.assertEqual(dashboard["stats"]["live_events"], 0)
        self.assertEqual(self.client.get("/api/academy/courses/").data["count"], 0)
        self.assertEqual(self.client.get(f"/api/academy/courses/{self.course.slug}/").status_code, 403)
        self.assertEqual(self.client.get(f"/api/academy/sessions/{self.session.pk}/").status_code, 403)
        self.assertEqual(self.client.get("/api/signals/?channel=CRYPTO").status_code, 403)
        self.assertEqual(self.client.get(f"/api/signals/{self.signal.pk}/").status_code, 403)
        self.assertEqual(self.client.get("/api/channels/internal-analysis/").status_code, 403)
        self.assertEqual(self.client.get(f"/api/channels/posts/{self.analysis.pk}/").status_code, 403)
        self.assertEqual(self.client.get("/api/livestream/").data["count"], 0)
        self.assertEqual(self.client.get(f"/api/livestream/{self.live.slug}/").status_code, 404)

        requested = self.client.post(
            "/api/accounts/market-access/requests/", {"requested_tier": "GOLD"}, format="json",
        )
        self.assertEqual(requested.status_code, 201)
        self.assertEqual(requested.data["requested_markets"], ["crypto"])
        self.assertEqual(self.dashboard()["content_access"]["academy_markets"], [])

        self.client.force_authenticate(self.admin)
        approved = self.client.patch(
            f"/api/accounts/admin/market-access/requests/{requested.data['id']}/review/",
            {"status": "APPROVED", "approved_markets": ["crypto"]}, format="json",
        )
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.data["status"], MarketAccessRequest.Status.APPROVED)
        self.assertEqual(NotificationSMSDelivery.objects.count(), 0)

        self.client.force_authenticate(self.user)
        dashboard = self.dashboard()
        self.assertEqual(dashboard["market_access_v2"]["approved_markets"], ["crypto"])
        self.assertEqual(dashboard["content_access"]["academy_markets"], ["crypto"])
        self.assertTrue(dashboard["content_access"]["signals"]["crypto"])
        self.assertTrue(dashboard["content_access"]["livestream"])
        self.assertFalse(dashboard["content_access"]["internal_opportunities"])
        self.assertEqual(self.client.get(f"/api/academy/courses/{self.course.slug}/").status_code, 200)
        self.assertEqual(self.client.get("/api/signals/?channel=CRYPTO").status_code, 200)
        self.assertEqual(self.client.get(f"/api/livestream/{self.live.slug}/").status_code, 200)
        self.assertEqual(self.client.get("/api/channels/internal-analysis/").status_code, 403)
        self.assertTrue(Notification.objects.filter(
            recipient=self.user,
            source_key=f"MARKET_ACCESS_REQUEST_APPROVED:{requested.data['id']}",
            show_in_app=True, send_sms=False,
        ).exists())

    def test_selected_market_remains_discoverable_before_trial_but_not_after(self):
        self.expire_trial()
        self.client.put(
            "/api/accounts/profile/market-preferences/",
            {"selected_markets": ["crypto", "forex", "internal"]}, format="json",
        )
        self.assertEqual(self.dashboard()["content_access"]["academy_markets"], [])
        self.assertEqual(self.client.get("/api/academy/courses/").data["count"], 0)

    def test_superadmin_bypasses_trial_expiry_gate(self):
        self.client.force_authenticate(self.admin)
        access = self.dashboard()["content_access"]
        self.assertTrue(access["livestream"])
        self.assertEqual(set(access["academy_markets"]), {"crypto", "forex", "internal"})

    def test_realtime_checks_expiry_and_do_not_leak_forex_analysis(self):
        channel_access = unwrap(ContentChannelConsumer.can_access)
        post_access = unwrap(ContentChannelConsumer.can_view_internal_post)
        live_access = unwrap(LivestreamConsumer.event_id)
        self.assertTrue(channel_access(None, self.user.pk, "internal-analysis"))
        self.assertEqual(live_access(None, self.live.slug, self.live.pk, self.user.pk), self.live.pk)
        self.expire_trial()
        self.assertFalse(channel_access(None, self.user.pk, "internal-analysis"))
        self.assertIsNone(live_access(None, self.live.slug, self.live.pk, self.user.pk))

        self.client.put(
            "/api/accounts/profile/market-preferences/",
            {"selected_markets": ["internal"]}, format="json",
        )
        requested = self.client.post(
            "/api/accounts/market-access/requests/", {"requested_tier": "GOLD"}, format="json",
        )
        self.client.force_authenticate(self.admin)
        self.client.patch(
            f"/api/accounts/admin/market-access/requests/{requested.data['id']}/review/",
            {"status": "APPROVED", "approved_markets": ["internal"]}, format="json",
        )
        self.assertTrue(channel_access(None, self.user.pk, "internal-analysis"))
        self.assertTrue(post_access(None, self.user.pk, self.analysis.pk))
        forex_analysis = ChannelPost.objects.create(
            channel=self.analysis.channel, author=self.admin, title="Forex private",
            body="Forex private body", scope=ChannelPost.Scope.FOREX,
            status=ChannelPost.Status.PUBLISHED, published_at=timezone.now(),
        )
        self.assertFalse(post_access(None, self.user.pk, forex_analysis.pk))
