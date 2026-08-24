from django.core.cache import cache
from rest_framework.test import APITestCase

from apps.accounts.models import User
from .models import SystemContent


class PlatformSettingsAPITests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="normal", password="pass")
        self.super_admin = User.objects.create_user(username="root-admin", password="pass", role=User.Role.SUPER_ADMIN)

    def test_public_settings_and_admin_permissions(self):
        self.assertEqual(self.client.get("/api/platform/settings/public/").status_code, 200)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get("/api/admin/platform/financial-settings/").status_code, 403)
        self.client.force_authenticate(self.super_admin)
        self.assertEqual(self.client.patch("/api/admin/platform/financial-settings/", {"minimum_deposit_irt": 20000}, format="json").status_code, 200)

    def test_seeded_content_can_be_updated(self):
        self.client.force_authenticate(self.super_admin)
        item = SystemContent.objects.first()
        response = self.client.patch(f"/api/admin/platform/content/{item.key}/", {"value": "Updated"}, format="json")
        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.value, "Updated")
