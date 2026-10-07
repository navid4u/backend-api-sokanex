from datetime import timedelta
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.academy.models import Course, CourseSession
from apps.notifications.models import Notification, NotificationSMSDelivery
from apps.notifications.services import NotificationService

from .models import TrialCampaign, TrialGrant, User, UserMarketGrant


@override_settings(MARKET_ACCESS_V2_ENABLED=True, CRM_ENABLED=False)
class BasicAccessV2Tests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="basic-admin", role=User.Role.SUPER_ADMIN)
        self.level_one = User.objects.create_user(username="basic-level-one", phone="09121110001")
        self.basic = User.objects.create_user(username="basic-member", phone="09121110002")
        UserMarketGrant.objects.create(
            user=self.basic, market=User.MarketType.CRYPTO,
            source=UserMarketGrant.Source.ADMIN, granted_by=self.admin,
        )

    def test_academy_is_basic_plus_and_ignores_legacy_level_flags_in_v2(self):
        course = Course.objects.create(
            title="Basic published course", instructor=self.admin,
            status=Course.Status.PUBLISHED, is_free=False, price=1000,
            allowed_level_1=False, allowed_level_2=False,
            allowed_level_3=False, allowed_level_4=False, allowed_level_5=False,
        )
        session = CourseSession.objects.create(
            course=course, title="Paid lesson", order=1, video_url="https://example.com/private"
        )
        self.client.force_authenticate(self.level_one)
        self.assertEqual(self.client.get("/api/academy/courses/").data["count"], 0)

        self.client.force_authenticate(self.basic)
        listing = self.client.get("/api/academy/courses/")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["count"], 1)
        # Basic visibility does not bypass the separate purchase/enrollment gate.
        detail = self.client.get(f"/api/academy/sessions/{session.pk}/")
        self.assertEqual(detail.status_code, 403)
        with override_settings(MARKET_ACCESS_V2_ENABLED=False):
            self.assertEqual(self.client.get("/api/academy/courses/").data["count"], 0)

    def test_v2_broadcasts_are_basic_plus_but_personal_messages_still_reach_level_one(self):
        broadcast = Notification.objects.create(
            title="General update", message="Visible to Basic+", created_by=self.admin,
            allowed_level_1=False, allowed_level_2=False,
            allowed_level_3=False, allowed_level_4=False, allowed_level_5=False,
        )
        personal = Notification.objects.create(
            title="Account alert", message="Personal", created_by=self.admin,
            recipient=self.level_one, allowed_level_1=False,
        )
        broadcast_users = set(NotificationService.audience_users(broadcast).values_list("pk", flat=True))
        self.assertIn(self.admin.pk, broadcast_users)
        self.assertIn(self.basic.pk, broadcast_users)
        self.assertNotIn(self.level_one.pk, broadcast_users)
        self.assertEqual(
            list(NotificationService.audience_users(personal).values_list("pk", flat=True)),
            [self.level_one.pk],
        )
        self.assertEqual(
            list(NotificationService.visible_notifications(self.level_one).values_list("pk", flat=True)),
            [personal.pk],
        )
        self.assertEqual(
            list(NotificationService.visible_notifications(self.basic).values_list("pk", flat=True)),
            [broadcast.pk],
        )

    def test_trial_temporarily_grants_basic_access_without_legacy_level_change(self):
        now = timezone.now()
        campaign = TrialCampaign.objects.create(created_by=self.admin)
        TrialGrant.objects.create(
            user=self.level_one, campaign=campaign,
            started_at=now, ends_at=now + timedelta(days=7),
        )
        broadcast = Notification.objects.create(
            title="Trial notice", message="Available", created_by=self.admin,
        )
        self.assertIn(self.level_one.pk, NotificationService.audience_users(broadcast).values_list("pk", flat=True))
        self.assertTrue(NotificationService.visible_notifications(self.level_one).filter(pk=broadcast.pk).exists())
        self.level_one.refresh_from_db()
        self.assertEqual(self.level_one.access_level, User.AccessLevel.LEVEL_1)

    def test_basic_access_matrix_keeps_general_api_open_and_vip_gated(self):
        self.client.force_authenticate(self.basic)
        for path in (
            "/api/accounts/profile/details/",
            "/api/dashboard/",
            "/api/wallet/",
            "/api/articles/",
            "/api/videos/",
            "/api/livestream/",
            "/api/academy/courses/",
            "/api/notifications/",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

        for path in ("/api/signals/", "/api/channels/internal-analysis/"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 403)

    @patch("apps.ai_assistant.views.AssistantService.financial", return_value=("پاسخ", {}))
    def test_assistant_is_basic_plus_in_v2_without_changing_legacy_gold_gate(self, financial):
        payload = {"messages": [{"role": "user", "content": "یک پرسش مالی"}]}
        self.client.force_authenticate(self.level_one)
        self.assertEqual(self.client.post("/api/assistant/chat/", payload, format="json").status_code, 403)
        self.assertEqual(self.client.post("/api/assistant/technical-analysis/", {}, format="multipart").status_code, 403)

        self.client.force_authenticate(self.basic)
        chat = self.client.post("/api/assistant/chat/", payload, format="json")
        self.assertEqual(chat.status_code, 200)
        self.assertEqual(chat.data["answer"], "پاسخ")
        financial.assert_called_once()
        # The missing image is a validation error, not a membership denial.
        self.assertEqual(self.client.post("/api/assistant/technical-analysis/", {}, format="multipart").status_code, 400)

        with override_settings(MARKET_ACCESS_V2_ENABLED=False):
            self.assertEqual(self.client.post("/api/assistant/chat/", payload, format="json").status_code, 403)

    @override_settings(PAYAMITO_SMS_SEND_INLINE=False)
    def test_broadcast_sms_queue_uses_v2_basic_audience_not_legacy_level_flags(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            "/api/notifications/",
            {"title": "V2 broadcast", "message": "Hello", "allowed_levels": [5], "send_sms": True},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        recipients = set(NotificationSMSDelivery.objects.values_list("user_id", flat=True))
        self.assertIn(self.basic.pk, recipients)
        self.assertNotIn(self.level_one.pk, recipients)
