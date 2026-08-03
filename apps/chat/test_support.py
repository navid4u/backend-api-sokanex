from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import SupportMessage, SupportThread


User = get_user_model()


class PrivateSupportAPITests(TestCase):
    def setUp(self):
        self.first = User.objects.create_user(username="support-user-1", password="StrongPass123!")
        self.second = User.objects.create_user(username="support-user-2", password="StrongPass123!")

    def test_each_user_only_sees_own_support_messages(self):
        first_client = APIClient()
        first_client.force_authenticate(self.first)
        self.assertEqual(first_client.post("/api/chat/support/messages/", {"text": "Private question"}).status_code, 201)

        second_client = APIClient()
        second_client.force_authenticate(self.second)
        response = second_client.get("/api/chat/support/messages/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 0)
        self.assertEqual(SupportThread.objects.count(), 2)
        self.assertEqual(SupportMessage.objects.count(), 1)

    def test_support_route_returns_support_slug(self):
        client = APIClient()
        client.force_authenticate(self.first)
        response = client.get("/api/chat/support/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["slug"], "support")

