import tempfile
from unittest.mock import patch
from unittest import skipUnless
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.core.management import call_command
from django.db import close_old_connections, connection, connections

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TransactionTestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.notifications.models import Notification, NotificationSMSDelivery
from apps.notifications.services import NotificationService
from common.sms import SMSProviderError

from .models import SupportMessage, SupportThread
from .serializers import SupportMessageSerializer
from .views import create_support_message


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class PrivateSupportAPITests(APITestCase):
    def setUp(self):
        self.support = User.objects.get(username="support")
        self.support.set_password("test-pass")
        self.support.is_active = True
        self.support.save(update_fields=["password", "is_active", "updated_at"])
        self.user = User.objects.create_user(
            username="09120000001", password="test-pass", first_name="Ali", last_name="Ahmadi"
        )
        self.other = User.objects.create_user(username="09120000002", password="test-pass")
        self.admin = User.objects.create_user(
            username="admin-test", password="test-pass", role=User.Role.SUPER_ADMIN, is_staff=True
        )

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def conversation(self, user=None):
        self.authenticate(user or self.user)
        response = self.client.get(reverse("support-conversation"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response

    def test_conversation_is_idempotent_and_assigned_to_support(self):
        first = self.conversation()
        second = self.client.get(reverse("support-conversation"))
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(first.data["assigned_to"]["username"], "support")
        self.assertEqual(SupportThread.objects.filter(user=self.user).count(), 1)

    def test_support_must_use_inbox_not_user_conversation_endpoint(self):
        self.authenticate(self.support)
        response = self.client.get(reverse("support-conversation"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_only_exact_support_account_can_access_inbox(self):
        self.conversation()
        for forbidden_user in (self.user,):
            self.authenticate(forbidden_user)
            response = self.client.get(reverse("support-queue"))
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.authenticate(self.support)
        response = self.client.get(reverse("support-queue"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.authenticate(self.admin)
        self.assertEqual(self.client.get(reverse("support-queue")).status_code, status.HTTP_200_OK)

    def test_user_cannot_read_or_post_to_another_conversation(self):
        conversation_id = self.conversation().data["id"]
        self.authenticate(self.other)
        detail = self.client.get(reverse("support-conversation-detail", args=[conversation_id]))
        post = self.client.post(
            reverse("support-conversation-messages", args=[conversation_id]), {"text": "intrusion"}
        )
        self.assertEqual(detail.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(post.status_code, status.HTTP_403_FORBIDDEN)

    def test_sender_cannot_be_forged(self):
        conversation_id = self.conversation().data["id"]
        response = self.client.post(
            reverse("support-conversation-messages", args=[conversation_id]),
            {"text": "hello", "sender": self.support.id},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(SupportMessage.objects.get().sender_id, self.user.id)

    def test_support_can_reply_and_unread_counts_are_viewer_specific(self):
        conversation_id = self.conversation().data["id"]
        self.client.post(
            reverse("support-conversation-messages", args=[conversation_id]), {"text": "customer message"}
        )
        self.authenticate(self.support)
        inbox = self.client.get(reverse("support-queue"))
        self.assertEqual(inbox.data["results"][0]["unread_count"], 1)
        reply = self.client.post(
            reverse("support-conversation-messages", args=[conversation_id]), {"text": "support reply"}
        )
        self.assertEqual(reply.status_code, status.HTTP_201_CREATED)
        self.authenticate(self.user)
        own = self.client.get(reverse("support-conversation"))
        self.assertEqual(own.data["unread_count"], 1)

    @override_settings(PAYAMITO_SMS_SEND_INLINE=True)
    @patch("apps.notifications.services.PayamitoSMSService.send")
    def test_support_reply_creates_one_private_notification_and_durable_sms(self, send):
        self.user.phone = "09120000001"
        self.user.save(update_fields=["phone", "updated_at"])
        conversation_id = self.conversation().data["id"]
        url = reverse("support-conversation-messages", args=[conversation_id])
        self.client.post(url, {"text": "customer question"}, format="json")
        self.authenticate(self.support)
        first = self.client.post(url, {"text": "private answer"}, format="json", HTTP_IDEMPOTENCY_KEY="reply-1")
        repeated = self.client.post(url, {"text": "private answer"}, format="json", HTTP_IDEMPOTENCY_KEY="reply-1")
        self.assertEqual((first.status_code, repeated.status_code), (201, 201))
        self.assertEqual(first.data["id"], repeated.data["id"])
        notification = Notification.objects.get(source_key=f"SUPPORT_REPLY:{first.data['id']}")
        self.assertEqual(notification.recipient_id, self.user.pk)
        self.assertEqual(notification.target_url, "/chat/support")
        self.assertEqual(notification.action_label, "مشاهده پاسخ")
        self.assertEqual(NotificationSMSDelivery.objects.filter(notification=notification).count(), 1)
        self.assertEqual(NotificationService.notification_sms_text(notification),
                         "پاسخ سؤال شما در سوکانکس داده شد.\nhttps://app.sokanex.com/chat/support")
        send.assert_not_called()
        self.authenticate(self.user)
        self.assertEqual(self.client.get("/api/notifications/").data["results"][0]["id"], notification.pk)
        self.assertEqual(self.client.get("/api/notifications/unread-count/").data["unread_count"], 1)
        self.assertEqual(self.client.get(f"/api/notifications/{notification.pk}/").status_code, 200)
        self.authenticate(self.other)
        self.assertEqual(self.client.get(f"/api/notifications/{notification.pk}/").status_code, 404)

    @patch("apps.notifications.services.PayamitoSMSService.send")
    def test_missing_phone_keeps_notification_and_provider_failure_keeps_message(self, send):
        conversation_id = self.conversation().data["id"]
        self.authenticate(self.support)
        url = reverse("support-conversation-messages", args=[conversation_id])
        response = self.client.post(url, {"text": "reply without phone"}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Notification.objects.filter(recipient=self.user).count(), 1)
        self.assertFalse(NotificationSMSDelivery.objects.exists())
        self.user.phone = "09120000001"
        self.user.save(update_fields=["phone", "updated_at"])
        response = self.client.post(url, {"text": "reply with phone"}, format="json")
        send.side_effect = SMSProviderError("temporary", provider_code="TEST")
        NotificationService.send_pending_sms()
        self.assertEqual(NotificationSMSDelivery.objects.get().status, NotificationSMSDelivery.Status.FAILED)
        self.assertTrue(SupportMessage.objects.filter(pk=response.data["id"]).exists())
        self.assertTrue(Notification.objects.filter(source_key=f"SUPPORT_REPLY:{response.data['id']}").exists())

    @patch("apps.notifications.services.PayamitoSMSService.send")
    def test_support_worker_filters_other_notification_sms(self, send):
        self.user.phone = "09120000001"
        self.user.save(update_fields=["phone", "updated_at"])
        conversation_id = self.conversation().data["id"]
        self.authenticate(self.support)
        self.client.post(
            reverse("support-conversation-messages", args=[conversation_id]),
            {"text": "support answer"}, format="json",
        )
        other = Notification.objects.create(
            title="Other", message="Other", recipient=self.user, send_sms=True,
        )
        NotificationService.queue_sms(other, allow_inline=False)
        send.return_value = {"message_id": "test-message-id"}
        call_command("retry_notification_sms", source_prefix="SUPPORT_REPLY:")
        self.assertEqual(send.call_count, 1)
        self.assertEqual(NotificationSMSDelivery.objects.get(notification=other).status,
                         NotificationSMSDelivery.Status.PENDING)

    def test_legacy_support_reply_uses_same_notification_path(self):
        thread = SupportThread.objects.create(user=self.user, assigned_to=self.support)
        self.authenticate(self.support)
        response = self.client.post(
            f'{reverse("support-messages")}?user_id={self.user.pk}',
            {"text": "legacy reply"}, format="json", HTTP_IDEMPOTENCY_KEY="legacy-1",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Notification.objects.filter(source_key=f"SUPPORT_REPLY:{response.data['id']}", recipient=self.user).exists())
        self.assertEqual(SupportMessage.objects.filter(thread=thread).count(), 1)

    def test_read_marks_only_other_senders_messages(self):
        conversation_id = self.conversation().data["id"]
        own = SupportMessage.objects.create(
            thread_id=conversation_id, sender=self.user, text="mine"
        )
        other = SupportMessage.objects.create(
            thread_id=conversation_id, sender=self.support, text="theirs"
        )
        response = self.client.post(reverse("support-conversation-read", args=[conversation_id]))
        self.assertEqual(response.data["unread_count"], 0)
        own.refresh_from_db()
        other.refresh_from_db()
        self.assertFalse(own.is_read)
        self.assertTrue(other.is_read)
        self.assertIsNotNone(other.read_at)

    def test_only_support_can_change_status_and_closed_ticket_reopens(self):
        conversation_id = self.conversation().data["id"]
        url = reverse("support-conversation-detail", args=[conversation_id])
        forbidden = self.client.patch(url, {"status": "closed"}, format="json")
        self.assertEqual(forbidden.status_code, status.HTTP_403_FORBIDDEN)
        self.authenticate(self.support)
        closed = self.client.patch(url, {"status": "closed"}, format="json")
        self.assertEqual(closed.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(closed.data["closed_at"])
        self.authenticate(self.user)
        self.client.post(
            reverse("support-conversation-messages", args=[conversation_id]), {"text": "reopen"}
        )
        thread = SupportThread.objects.get(pk=conversation_id)
        self.assertEqual(thread.status, SupportThread.Status.OPEN)
        self.assertIsNone(thread.closed_at)

    def test_valid_attachment_upload_and_executable_rejection(self):
        conversation_id = self.conversation().data["id"]
        url = reverse("support-conversation-messages", args=[conversation_id])
        valid = SimpleUploadedFile("note.txt", b"safe", content_type="text/plain")
        response = self.client.post(url, {"attachment": valid}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        executable = SimpleUploadedFile(
            "malware.exe", b"MZ", content_type="application/octet-stream"
        )
        response = self.client.post(url, {"attachment": executable}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_search_status_ordering_and_page_size(self):
        thread = SupportThread.objects.create(
            user=self.user,
            assigned_to=self.support,
            status=SupportThread.Status.PENDING,
        )
        self.authenticate(self.support)
        response = self.client.get(
            reverse("support-queue"), {"search": "Ali", "status": "pending", "page_size": 1}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], thread.id)

    def test_legacy_support_operator_can_select_user_and_reply(self):
        thread = SupportThread.objects.create(user=self.user, assigned_to=self.support)
        self.authenticate(self.support)
        detail = self.client.get(
            reverse("support-thread"), {"user_id": self.user.id}
        )
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(detail.data["id"], thread.id)
        reply = self.client.post(
            f'{reverse("support-messages")}?user_id={self.user.id}',
            {"text": "legacy support reply", "sender": self.user.id},
            format="multipart",
        )
        self.assertEqual(reply.status_code, status.HTTP_201_CREATED)
        message = SupportMessage.objects.get(text="legacy support reply")
        self.assertEqual(message.sender_id, self.support.id)
        self.assertEqual(message.thread_id, thread.id)

    def test_legacy_user_id_is_forbidden_for_users_but_allowed_for_superadmin(self):
        self.authenticate(self.user)
        detail = self.client.get(
            reverse("support-thread"), {"user_id": self.other.id}
        )
        post = self.client.post(
            f'{reverse("support-messages")}?user_id={self.other.id}',
            {"text": "forbidden"},
            format="json",
        )
        self.assertEqual(detail.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(post.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(SupportMessage.objects.filter(text="forbidden").exists())

        self.authenticate(self.admin)
        detail = self.client.get(
            reverse("support-thread"), {"user_id": self.other.id}
        )
        post = self.client.post(
            f'{reverse("support-messages")}?user_id={self.other.id}',
            {"text": "superadmin reply"},
            format="json",
        )
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(post.status_code, status.HTTP_201_CREATED)

    def test_legacy_messages_keep_multipart_attachment_support(self):
        self.authenticate(self.user)
        attachment = SimpleUploadedFile("legacy.txt", b"legacy", content_type="text/plain")
        response = self.client.post(
            reverse("support-messages"),
            {"text": "with attachment", "attachment": attachment},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        message = SupportMessage.objects.get(text="with attachment")
        self.assertTrue(bool(message.attachment))
        self.assertEqual(message.sender_id, self.user.id)
        self.assertIsNotNone(message.thread.last_message_at)


@skipUnless(connection.vendor == "postgresql", "Row-lock concurrency is PostgreSQL-specific")
@override_settings(PAYAMITO_SMS_SEND_INLINE=False)
class ConcurrentSupportReplyTests(TransactionTestCase):
    def test_same_idempotency_key_creates_one_message_notification_and_outbox(self):
        support = User.objects.get(username="support")
        recipient = User.objects.create_user(username="support-race-recipient", phone="09120000001")
        thread = SupportThread.objects.create(user=recipient, assigned_to=support)
        barrier = Barrier(2)

        def submit():
            close_old_connections()
            try:
                serializer = SupportMessageSerializer(data={"text": "concurrent reply"})
                serializer.is_valid(raise_exception=True)
                barrier.wait(timeout=10)
                message, created = create_support_message(serializer, thread, support, "same-key")
                return message.pk, created
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(submit)
            second = pool.submit(submit)
            results = [first.result(timeout=30), second.result(timeout=30)]
        self.assertEqual(results[0][0], results[1][0])
        self.assertEqual(sorted(created for _, created in results), [False, True])
        self.assertEqual(Notification.objects.filter(source_key=f"SUPPORT_REPLY:{results[0][0]}").count(), 1)
        self.assertEqual(NotificationSMSDelivery.objects.count(), 1)
