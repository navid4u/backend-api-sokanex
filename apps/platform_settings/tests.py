from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.accounts.models import PlatformRole, User
from .models import SystemContent, UITranslationAuditLog, UITranslationCatalog


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


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class TranslationCatalogAPITests(APITestCase):
    admin_url = "/api/admin/platform/translations/"
    public_url = "/api/platform/translations/en/"

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="translation-user", password="pass")
        self.super_admin = User.objects.create_user(
            username="translation-admin", password="pass", role=User.Role.SUPER_ADMIN
        )

    def test_admin_permission_and_exact_response(self):
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get(self.admin_url).status_code, 403)
        self.client.force_authenticate(self.super_admin)
        response = self.client.get(self.admin_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data), {"locale", "version", "translations", "updated_at"})
        self.assertEqual(response.data["locale"], "en")
        role = PlatformRole.objects.create(
            name="Platform translators", slug="platform-translators",
            permissions=[User.Permission.PLATFORM_SETTINGS_MANAGE],
        )
        manager = User.objects.create_user(username="translation-manager", custom_role=role)
        self.client.force_authenticate(manager)
        self.assertEqual(self.client.get(self.admin_url).status_code, 200)

    def test_replace_is_atomic_versions_and_audits(self):
        self.client.force_authenticate(self.super_admin)
        payload = {"translations": {"خانه": "Home", "ورود به سوکانکس": "Sign in to Sokanex"}}
        first = self.client.patch(self.admin_url, payload, format="json")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data["version"], 2)
        self.assertEqual(first.data["translations"], payload["translations"])
        second = self.client.patch(self.admin_url, {"translations": {"خروج": "Sign out"}}, format="json")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data["version"], 3)
        self.assertNotIn("خانه", second.data["translations"])
        audit = UITranslationAuditLog.objects.latest("id")
        self.assertEqual((audit.previous_version, audit.new_version), (2, 3))
        self.assertEqual(audit.actor, self.super_admin)

    def test_validation_rejects_non_strings_html_and_long_values(self):
        self.client.force_authenticate(self.super_admin)
        for translations in (
            {"خانه": 12},
            {"خانه": "<script>alert(1)</script>"},
            {"<img src=x onerror=alert(1)>": "Home"},
            {"خانه": "x" * 1001},
        ):
            response = self.client.patch(self.admin_url, {"translations": translations}, format="json")
            self.assertEqual(response.status_code, 400)
        self.assertEqual(UITranslationAuditLog.objects.count(), 0)

    @override_settings(TRANSLATIONS_MAX_PAYLOAD_BYTES=100)
    def test_oversized_payload_is_rejected(self):
        self.client.force_authenticate(self.super_admin)
        response = self.client.patch(
            self.admin_url, {"translations": {"عبارت": "x" * 90}}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_public_response_cache_etag_and_invalidation(self):
        catalog = UITranslationCatalog.load("en")
        catalog.translations = {"خانه": "Home"}
        catalog.save()
        first = self.client.get(self.public_url)
        self.assertEqual(first.status_code, 200)
        self.assertIn("public, max-age=120", first["Cache-Control"])
        self.assertTrue(first["ETag"].startswith('"'))
        self.assertNotIn("updated_by", first.data)
        conditional = self.client.get(self.public_url, HTTP_IF_NONE_MATCH=first["ETag"])
        self.assertEqual(conditional.status_code, 304)

        self.client.force_authenticate(self.super_admin)
        changed = self.client.patch(
            self.admin_url, {"translations": {"خانه": "Homepage"}}, format="json"
        )
        self.assertEqual(changed.status_code, 200)
        self.client.force_authenticate(user=None)
        refreshed = self.client.get(self.public_url)
        self.assertEqual(refreshed.data["translations"]["خانه"], "Homepage")
        self.assertNotEqual(refreshed["ETag"], first["ETag"])

    def test_unknown_locale_is_404(self):
        self.assertEqual(self.client.get("/api/platform/translations/fa/").status_code, 404)
