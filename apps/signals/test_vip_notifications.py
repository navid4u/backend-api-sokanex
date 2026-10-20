from datetime import timedelta

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import TrialCampaign, TrialGrant, User, UserMarketGrant
from apps.notifications.models import Notification
from apps.notifications.services import NotificationService


@override_settings(
    MARKET_ACCESS_V2_ENABLED=True,
    SIGNAL_CHANNEL_INGESTION_API_KEY="test-vip-ingest-key",
)
class VIPSignalNotificationTests(APITestCase):
    def setUp(self):
        User.objects.get_or_create(
            username="sokanex-feed-bot", defaults={"is_active": False},
        )
        self.admin = User.objects.create_user(username="vip-alert-admin", role=User.Role.SUPER_ADMIN)
        self.crypto = User.objects.create_user(username="vip-alert-crypto")
        self.forex = User.objects.create_user(username="vip-alert-forex")
        self.trial = User.objects.create_user(username="vip-alert-trial")
        UserMarketGrant.objects.create(
            user=self.crypto, market="crypto", source=UserMarketGrant.Source.ADMIN,
            granted_by=self.admin,
        )
        UserMarketGrant.objects.create(
            user=self.forex, market="forex", source=UserMarketGrant.Source.ADMIN,
            granted_by=self.admin,
        )
        campaign = TrialCampaign.objects.create(created_by=self.admin)
        now = timezone.now()
        TrialGrant.objects.create(
            user=self.trial, campaign=campaign,
            started_at=now - timedelta(hours=1), ends_at=now + timedelta(days=6),
        )

    def test_ingest_creates_one_safe_market_scoped_notification(self):
        url = "/api/signals/channels/crypto/ingest/"
        payload = {"external_id": "telegram:crypto:100", "text": "خصوصی و محرمانه"}
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                url, payload, format="multipart",
                HTTP_X_SOKANEX_SIGNAL_KEY="test-vip-ingest-key",
            )
        self.assertEqual(response.status_code, 201, response.data)
        notification = Notification.objects.get(source_key=f"VIP_SIGNAL:{response.data['id']}")
        self.assertEqual(notification.market_scope, "crypto")
        self.assertNotIn("محرمانه", notification.message)
        self.assertTrue(NotificationService.visible_notifications(self.crypto).filter(pk=notification.pk).exists())
        self.assertTrue(NotificationService.visible_notifications(self.trial).filter(pk=notification.pk).exists())
        self.assertTrue(NotificationService.visible_notifications(self.admin).filter(pk=notification.pk).exists())
        self.assertFalse(NotificationService.visible_notifications(self.forex).filter(pk=notification.pk).exists())
        recipients = set(NotificationService.audience_users(notification).values_list("pk", flat=True))
        self.assertIn(self.crypto.pk, recipients)
        self.assertIn(self.trial.pk, recipients)
        self.assertNotIn(self.forex.pk, recipients)

        with self.captureOnCommitCallbacks(execute=True):
            retry = self.client.post(
                url, payload, format="multipart",
                HTTP_X_SOKANEX_SIGNAL_KEY="test-vip-ingest-key",
            )
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(Notification.objects.filter(source_key=notification.source_key).count(), 1)

    def test_expired_trial_cannot_receive_market_notification_from_old_grant(self):
        grant = TrialGrant.objects.get(user=self.trial)
        old_access = UserMarketGrant.objects.create(
            user=self.trial, market="crypto", source=UserMarketGrant.Source.ADMIN,
            granted_by=self.admin, granted_at=grant.started_at + timedelta(hours=1),
        )
        now = timezone.now()
        TrialGrant.objects.filter(pk=grant.pk).update(
            started_at=now - timedelta(days=8), ends_at=now - timedelta(days=1),
        )
        old_access.granted_at = now - timedelta(days=7)
        old_access.save(update_fields=("granted_at",))
        self.trial.refresh_from_db()
        notification = Notification.objects.create(
            title="Crypto", message="New VIP post", notification_type=Notification.Type.SIGNAL,
            market_scope="crypto",
        )
        self.assertFalse(NotificationService.visible_notifications(self.trial).filter(pk=notification.pk).exists())
        self.assertNotIn(
            self.trial.pk,
            NotificationService.audience_users(notification).values_list("pk", flat=True),
        )
        old_access.revoked_at = now
        old_access.save(update_fields=("revoked_at",))
        UserMarketGrant.objects.create(
            user=self.trial, market="crypto", source=UserMarketGrant.Source.ADMIN,
            granted_by=self.admin, granted_at=now,
        )
        self.assertTrue(NotificationService.visible_notifications(self.trial).filter(pk=notification.pk).exists())
