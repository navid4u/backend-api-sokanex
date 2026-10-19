from datetime import date, datetime, timedelta, timezone as utc_timezone
from io import StringIO
from uuid import uuid4

from django.core.cache import cache
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import User, UserAccessProfile, UserMarketGrant
from apps.accounts.market_access_requests import submit_market_access_request
from apps.accounts.market_preferences import update_market_preferences
from apps.observability.models import LogEvent

from .analytics import TEHRAN, gregorian_to_jalali, overview
from .models import PageViewDailyAggregate, PageViewEvent, PageViewReceipt, UserActivity


@override_settings(CRM_ENABLED=False)
class AdminAnalyticsTests(APITestCase):
    overview_url = "/api/accounts/admin/analytics/overview/"
    views_url = "/api/activity/page-views/"

    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_user(username="analytics-super", role=User.Role.SUPER_ADMIN)
        self.support = User.objects.create_user(username="analytics-support", role=User.Role.SUPPORT)
        self.user = User.objects.create_user(username="analytics-user", market_type="crypto")

    def event(self, path="/signals", event_id=None):
        return {"event_id": str(event_id or uuid4()), "session_id": str(uuid4()), "path": path}

    def test_permissions_period_and_dashboard_gate(self):
        self.assertEqual(self.client.get(self.overview_url).status_code, 401)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get(self.overview_url).status_code, 403)
        self.assertFalse(self.client.get("/api/dashboard/").data["data"]["analytics_tracking"]["enabled"])
        self.client.force_authenticate(self.support)
        self.assertEqual(self.client.get(self.overview_url).status_code, 403)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(self.overview_url, {"period": "nonsense"}).status_code, 400)
        result = self.client.get(self.overview_url)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["period"], "6m")
        self.assertEqual(len(result.data["registrations"]), 6)
        self.assertEqual(result.data["total_users"], User.objects.count())
        self.assertEqual(result.data["page_views"]["total_views"], 0)
        self.assertIsNone(result.data["metadata"]["page_view_coverage_started_at"])
        self.assertIn("no-store", result["Cache-Control"])

    def test_user_list_count_includes_inactive_and_real_order(self):
        self.user.is_active = False
        self.user.save(update_fields=("is_active",))
        older = timezone.now() - timedelta(days=2)
        User.objects.filter(pk=self.user.pk).update(created_at=older)
        self.client.force_authenticate(self.admin)
        result = self.client.get("/api/accounts/users/", {"ordering": "-created_at", "page_size": 1})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["count"], User.objects.count())
        self.assertEqual(len(result.data["results"]), 1)
        self.assertIsNotNone(result.data["results"][0]["created_at"])
        self.assertNotEqual(result.data["results"][0]["id"], self.user.pk)
        filtered = self.client.get("/api/accounts/users/", {"is_active": "false"})
        self.assertEqual(filtered.data["count"], User.objects.filter(is_active=False).count())

    def test_jalali_month_and_day_boundaries_are_complete(self):
        self.assertEqual(gregorian_to_jalali(date(2026, 3, 20)), (1404, 12, 29))
        self.assertEqual(gregorian_to_jalali(date(2026, 3, 21)), (1405, 1, 1))
        now = datetime(2026, 3, 21, 12, tzinfo=TEHRAN).astimezone(utc_timezone.utc)
        User.objects.filter(pk=self.user.pk).update(created_at=datetime(2026, 3, 20, 23, tzinfo=TEHRAN))
        monthly = overview("3m", now=now)
        self.assertEqual(len(monthly["registrations"]), 3)
        self.assertEqual(monthly["registrations"][-2]["label"], "اسفند ۱۴۰۴")
        self.assertEqual(monthly["registrations"][-1]["label"], "فروردین ۱۴۰۵")
        self.assertEqual(monthly["registrations"][-2]["count"], 1)
        self.assertEqual(sum(item["count"] for item in monthly["registrations"]), 1)
        daily = overview("7d", now=now)
        self.assertEqual(len(daily["registrations"]), 7)
        self.assertEqual(daily["registrations"][-2]["count"], 1)
        self.assertEqual(daily["registrations"][-1]["count"], 0)
        for period, expected in (("1m", 1), ("6m", 6), ("12m", 12), ("30d", 30)):
            self.assertEqual(len(overview(period, now=now)["registrations"]), expected)

    def test_tracking_off_validation_dedup_and_unique_users(self):
        self.client.force_authenticate(self.user)
        payload = self.event()
        self.assertEqual(self.client.post(self.views_url, payload, format="json").status_code, 202)
        self.assertFalse(PageViewEvent.objects.exists())
        with override_settings(ANALYTICS_PAGE_VIEW_TRACKING_ENABLED=True):
            self.assertTrue(self.client.get("/api/dashboard/").data["data"]["analytics_tracking"]["enabled"])
            self.assertEqual(self.client.post(self.views_url, payload, format="json").status_code, 201)
            self.assertEqual(self.client.post(self.views_url, payload, format="json").status_code, 200)
            self.assertEqual(self.client.post(self.views_url, {**payload, "path": "/academy"}, format="json").status_code, 400)
            for bad in ("/login", "/admin", "/signals?token=secret", "/articles/private-slug"):
                self.assertEqual(self.client.post(self.views_url, self.event(bad), format="json").status_code, 400)
            self.assertEqual(self.client.post(self.views_url, {**self.event(), "user_id": self.admin.pk}, format="json").status_code, 400)
            self.assertFalse(LogEvent.objects.filter(path=self.views_url).exists())
            self.assertEqual(self.client.post(self.views_url, self.event("/signals"), format="json").status_code, 201)
            self.assertEqual(self.client.post(self.views_url, self.event("/academy"), format="json").status_code, 201)
            self.client.force_authenticate(self.support)
            self.assertEqual(self.client.post(self.views_url, self.event("/signals"), format="json").status_code, 201)
        self.assertEqual(PageViewEvent.objects.count(), 4)
        self.assertEqual(PageViewReceipt.objects.count(), 4)
        self.assertEqual(PageViewDailyAggregate.objects.count(), 3)
        snapshot = overview("7d", now=timezone.now())
        self.assertEqual(snapshot["page_views"]["total_views"], 4)
        self.assertEqual(snapshot["page_views"]["unique_users"], 2)
        self.assertEqual(snapshot["page_views"]["results"][0]["unique_users"], 2)

    @override_settings(ANALYTICS_PAGE_VIEW_TRACKING_ENABLED=True)
    def test_exact_per_user_rate_limit_and_anonymous_rejection(self):
        self.assertEqual(self.client.post(self.views_url, self.event(), format="json").status_code, 401)
        self.client.force_authenticate(self.user)
        for _ in range(60):
            self.assertEqual(self.client.post(self.views_url, self.event(), format="json").status_code, 201)
        self.assertEqual(self.client.post(self.views_url, self.event(), format="json").status_code, 429)
        self.assertEqual(PageViewEvent.objects.count(), 60)
        self.assertFalse(LogEvent.objects.filter(path=self.views_url).exists())

    @override_settings(ANALYTICS_PAGE_VIEW_TRACKING_ENABLED=True)
    def test_repeated_event_requests_are_also_throttled(self):
        self.client.force_authenticate(self.user)
        payload = self.event()
        self.assertEqual(self.client.post(self.views_url, payload, format="json").status_code, 201)
        for _ in range(59):
            self.assertEqual(self.client.post(self.views_url, payload, format="json").status_code, 200)
        self.assertEqual(self.client.post(self.views_url, payload, format="json").status_code, 429)
        self.assertEqual(PageViewEvent.objects.count(), 1)

    def test_v2_tiers_are_exclusive_and_not_legacy_level(self):
        with override_settings(MARKET_ACCESS_V2_ENABLED=True):
            before = overview("1m", now=timezone.now())
        before_tiers = {item["label"]: item["count"] for item in before["distributions"]["tiers"]}
        UserMarketGrant.objects.create(user=self.user, market="crypto", source="ADMIN", granted_by=self.admin)
        UserAccessProfile.objects.create(user=self.support, is_elite=True)
        with override_settings(MARKET_ACCESS_V2_ENABLED=True):
            result = overview("1m", now=timezone.now())
        tiers = {item["label"]: item["count"] for item in result["distributions"]["tiers"]}
        self.assertEqual(tiers["پایه"], before_tiers["پایه"] + 1)
        self.assertEqual(tiers["حساب مدیریتی"], before_tiers["حساب مدیریتی"])
        self.assertEqual(sum(tiers.values()), User.objects.count())
        self.assertEqual(result["metadata"]["tier_source"], "market_access_v2")
        legacy = overview("1m", now=timezone.now())
        self.assertEqual(legacy["metadata"]["tier_source"], "legacy_access_level")
        self.assertEqual(sum(item["count"] for item in legacy["distributions"]["tiers"]), User.objects.count())

    def test_only_provable_activity_is_exposed_without_sensitive_metadata(self):
        UserActivity.objects.create(user=self.user, activity_type=UserActivity.Type.REGISTER,
                                    title="Sensitive phone", metadata={"otp": "1234"}, target_url="/private/123")
        UserActivity.objects.create(user=self.user, activity_type=UserActivity.Type.SECURITY, title="Error")
        result = overview("7d", now=timezone.now())
        self.assertEqual(len(result["user_events"]), 1)
        item = result["user_events"][0]
        self.assertEqual(item["activity_type"], "REGISTER")
        self.assertEqual(item["title"], "ثبت‌نام کاربر")
        self.assertEqual(item["path"], "/admin/users")
        self.assertNotIn("otp", str(item))

    def test_market_events_are_written_only_for_real_changes(self):
        with override_settings(MARKET_ACCESS_V2_ENABLED=True):
            update_market_preferences(user=self.user, selected_markets=["crypto"])
            update_market_preferences(user=self.user, selected_markets=["crypto"])
            first, created = submit_market_access_request(user=self.user, requested_tier="GOLD")
            second, repeated = submit_market_access_request(user=self.user, requested_tier="GOLD")
        self.assertTrue(created)
        self.assertFalse(repeated)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(UserActivity.objects.filter(user=self.user, activity_type=UserActivity.Type.MARKET_PREFERENCES_UPDATE).count(), 1)
        self.assertEqual(UserActivity.objects.filter(user=self.user, activity_type=UserActivity.Type.MARKET_ACCESS_REQUEST).count(), 1)
        events = overview("7d", now=timezone.now())["user_events"]
        self.assertTrue(any(row["activity_type"] == "MARKET_ACCESS_REQUEST" for row in events))

    def test_retention_does_not_delete_unaggregated_or_other_data(self):
        old = timezone.now() - timedelta(days=31)
        aggregated = PageViewEvent.objects.create(user=self.user, event_id=uuid4(), session_id=uuid4(), path="/signals", aggregated_at=old)
        receipt = PageViewReceipt.objects.create(user=self.user, event_id=aggregated.event_id)
        expired_receipt = PageViewReceipt.objects.create(user=self.user, event_id=uuid4())
        PageViewReceipt.objects.filter(pk=expired_receipt.pk).update(created_at=timezone.now() - timedelta(days=401))
        pending = PageViewEvent.objects.create(user=self.user, event_id=uuid4(), session_id=uuid4(), path="/academy")
        PageViewEvent.objects.filter(pk__in=(aggregated.pk, pending.pk)).update(created_at=old)
        daily = PageViewDailyAggregate.objects.create(user=self.user, path="/signals", day=timezone.localdate() - timedelta(days=401), views=1)
        activity = UserActivity.objects.create(user=self.user, activity_type=UserActivity.Type.REGISTER, title="Preserve me")
        call_command("purge_page_view_analytics", stdout=StringIO())
        self.assertEqual(PageViewEvent.objects.count(), 2)
        call_command("purge_page_view_analytics", apply=True, stdout=StringIO())
        self.assertFalse(PageViewEvent.objects.filter(pk=aggregated.pk).exists())
        self.assertTrue(PageViewEvent.objects.filter(pk=pending.pk).exists())
        self.assertFalse(PageViewDailyAggregate.objects.filter(pk=daily.pk).exists())
        self.assertTrue(PageViewReceipt.objects.filter(pk=receipt.pk).exists())
        self.assertFalse(PageViewReceipt.objects.filter(pk=expired_receipt.pk).exists())
        self.assertTrue(UserActivity.objects.filter(pk=activity.pk).exists())
        self.client.force_authenticate(self.user)
        with override_settings(ANALYTICS_PAGE_VIEW_TRACKING_ENABLED=True):
            self.assertEqual(self.client.post(self.views_url, {
                "event_id": str(aggregated.event_id), "session_id": str(uuid4()), "path": "/signals",
            }, format="json").status_code, 200)
        self.assertFalse(PageViewEvent.objects.filter(pk=aggregated.pk).exists())
