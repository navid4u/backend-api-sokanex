from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import BrokerConnection, User
from apps.academy.models import Course, CourseEnrollment, CourseSession, Quiz, QuizOption, QuizQuestion
from apps.chat.models import SupportThread
from apps.content_channels.models import Channel, ChannelPost
from apps.signals.models import Signal, SignalStatus


class FrontendV2ContractTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="v2-user", password="StrongPass123!", access_level=User.AccessLevel.LEVEL_5,
        )
        self.admin = User.objects.create_superuser(
            username="v2-admin", password="StrongPass123!", email="admin@example.com",
        )

    def auth(self, user=None):
        self.client.force_authenticate(user or self.user)

    def test_broker_connection_and_finance_dashboard(self):
        self.auth()
        document = SimpleUploadedFile("account.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        response = self.client.post(
            "/api/accounts/broker-connection/",
            {"broker_name": "Licensed Broker", "account_number": "A-123", "referral_code": "REF", "document": document},
            format="multipart",
        )
        self.assertEqual(response.status_code, 201)
        connection = BrokerConnection.objects.get(user=self.user)
        self.auth(self.admin)
        response = self.client.patch(
            f"/api/accounts/admin/broker-connections/{connection.pk}/review/",
            {"status": "connected", "balance": "100.00", "equity": "120.00", "currency": "USD", "chart": [90, 100, 120]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.auth()
        dashboard = self.client.get("/api/dashboard/")
        self.assertEqual(dashboard.status_code, 200)
        self.assertTrue(dashboard.data["data"]["finance"]["connected"])

    def test_market_never_returns_fake_quotes_without_provider(self):
        self.auth()
        response = self.client.get("/api/market/quotes/?symbols=usd-irr")
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.data["success"])

    def test_signal_updates_are_persisted_and_embedded(self):
        signal = Signal.objects.create(
            title="Gold", symbol="XAUUSD", market="gold", direction="buy",
            entry_price=100, stop_loss=90, take_profit=120,
            status=SignalStatus.ACTIVE, created_by=self.user,
        )
        self.auth()
        response = self.client.post(
            f"/api/signals/{signal.pk}/updates/",
            {"title": "Risk Free", "message": "Move stop loss", "status": "successful"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        detail = self.client.get(f"/api/signals/{signal.pk}/")
        self.assertEqual(detail.data["updates"][0]["title"], "Risk Free")

    def test_channel_access_post_and_short_lived_ticket(self):
        channel = Channel.objects.get(slug="vip-signals")
        ChannelPost.objects.create(
            channel=channel, title="Real post", body="Analysis", author=self.admin,
            published_at=timezone.now(),
        )
        self.auth()
        response = self.client.get("/api/channels/vip-signals/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["title"], "Real post")
        ticket = self.client.post("/api/channels/ticket/", {"channel": "vip-signals"}, format="json")
        self.assertEqual(ticket.status_code, 200)
        self.assertIn("ticket", ticket.data)

    def test_support_conversation_is_object_scoped(self):
        self.auth()
        mine = self.client.get("/api/support/conversation/")
        self.assertEqual(mine.status_code, 200)
        other = User.objects.create_user(username="other-v2", password="StrongPass123!")
        other_thread = SupportThread.objects.create(user=other)
        denied = self.client.get(f"/api/support/conversations/{other_thread.pk}/messages/")
        self.assertEqual(denied.status_code, 403)

    def test_quiz_attempt_does_not_expose_correct_answers(self):
        course = Course.objects.create(title="Course", instructor=self.admin, status=Course.Status.PUBLISHED)
        session = CourseSession.objects.create(course=course, title="Session", order=1, media_type="text")
        CourseEnrollment.objects.create(user=self.user, course=course)
        quiz = Quiz.objects.create(session=session, title="Quiz", required_score=50)
        question = QuizQuestion.objects.create(quiz=quiz, text="Question")
        correct = QuizOption.objects.create(question=question, text="Correct", is_correct=True)
        QuizOption.objects.create(question=question, text="Wrong", is_correct=False)
        self.auth()
        public = self.client.get(f"/api/academy/sessions/{session.pk}/quiz/")
        self.assertEqual(public.status_code, 200)
        self.assertNotIn("is_correct", public.data["questions"][0]["options"][0])
        attempt = self.client.post(
            f"/api/academy/quizzes/{quiz.pk}/attempts/",
            {"answers": {str(question.pk): correct.pk}}, format="json",
        )
        self.assertEqual(attempt.status_code, 201)
        self.assertTrue(attempt.data["passed"])
