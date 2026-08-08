from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import UserDevice


class RefreshRotationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="rotate-user", password="StrongPass123!")
        self.client = APIClient()

    def test_refresh_rotates_token_and_updates_registered_device(self):
        login = self.client.post(
            "/api/token/", {"username": "rotate-user", "password": "StrongPass123!"},
            format="json", HTTP_X_DEVICE_ID="browser-1",
        )
        old_refresh = login.data["refresh"]
        device = UserDevice.objects.get(user=self.user, device_id="browser-1")
        old_jti = device.refresh_jti

        response = self.client.post("/api/token/refresh/", {"refresh": old_refresh}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertNotEqual(response.data["refresh"], old_refresh)
        device.refresh_from_db()
        self.assertNotEqual(device.refresh_jti, old_jti)

        replay = self.client.post("/api/token/refresh/", {"refresh": old_refresh}, format="json")
        self.assertEqual(replay.status_code, 401)
