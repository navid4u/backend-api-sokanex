from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Badge, UserDevice


User = get_user_model()


class SecurityAndBadgeAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="secure-user", email="secure@example.com", password="StrongPass123!"
        )
        self.admin = User.objects.create_user(
            username="secure-admin", password="StrongPass123!", role=User.Role.ADMIN
        )

    def test_login_registers_device_and_returns_device_id(self):
        client = APIClient()
        response = client.post(
            "/api/token/",
            {"username": "secure-user", "password": "StrongPass123!"},
            HTTP_X_DEVICE_NAME="Firefox on Windows",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("device_id", response.data)
        self.assertTrue(UserDevice.objects.filter(user=self.user).exists())

    def test_admin_can_award_badge_and_user_can_see_it(self):
        badge = Badge.objects.create(name="First Step")
        admin_client = APIClient()
        admin_client.force_authenticate(self.admin)
        response = admin_client.post(
            f"/api/accounts/users/{self.user.id}/badges/",
            {"badge_id": badge.id, "note": "Welcome"},
        )
        self.assertEqual(response.status_code, 201)
        user_client = APIClient()
        user_client.force_authenticate(self.user)
        response = user_client.get("/api/accounts/badges/mine/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]["badge"]["name"], "First Step")

