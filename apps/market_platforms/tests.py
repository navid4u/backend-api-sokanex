from io import BytesIO
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from rest_framework.test import APITestCase

from apps.accounts.models import User

from .models import FieldDefinition, Platform, PlatformChangeAudit


def logo_file(name="logo.png"):
    output = BytesIO()
    Image.new("RGB", (2, 2), "red").save(output, format="PNG")
    return SimpleUploadedFile(name, output.getvalue(), content_type="image/png")


class MarketPlatformAPITests(APITestCase):
    def setUp(self):
        media_root = TemporaryDirectory()
        self.addCleanup(media_root.cleanup)
        media_override = override_settings(MEDIA_ROOT=media_root.name)
        media_override.enable()
        self.addCleanup(media_override.disable)
        self.admin = User.objects.create_user(username="platform-admin", role=User.Role.SUPER_ADMIN)
        self.user = User.objects.create_user(username="platform-reader", access_level=1)
        self.broker = Platform.objects.create(platform_type="BROKER", name="Alpha Broker", rating="4.5",
                                              details={"regulation": "A", "pros": "Fast"})
        self.exchange = Platform.objects.create(platform_type="EXCHANGE", name="Beta Exchange", rating="3.0")

    def test_seed_definitions_and_public_auth_for_all_levels(self):
        self.assertEqual(FieldDefinition.objects.filter(platform_type="BROKER").count(), 10)
        self.assertEqual(FieldDefinition.objects.filter(platform_type="EXCHANGE").count(), 10)
        self.assertIn(self.client.get("/api/market-platforms/").status_code, (401, 403))
        self.client.force_authenticate(self.user)
        with override_settings(MARKET_ACCESS_V2_ENABLED=True):
            response = self.client.get("/api/market-platforms/?platform_type=BROKER")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["count"], 1)
            self.assertEqual(response.data["results"][0]["details"]["regulation"], "A")
            self.assertNotIsInstance(response.data["results"][0]["rating"], str)
            self.assertEqual(self.client.get(f"/api/market-platforms/{self.broker.pk}/").status_code, 200)
        self.assertEqual(self.client.get("/api/market-platforms/fields/?platform_type=BROKER").data["count"], 10)
        self.assertEqual(self.client.get("/api/market-platforms/manage/").status_code, 403)
        self.assertEqual(self.client.post("/api/market-platforms/manage/", {"name": "Denied"}).status_code, 403)

    def test_list_filter_sort_pagination_and_inactive(self):
        self.client.force_authenticate(self.user)
        other = Platform.objects.create(platform_type="BROKER", name="Zulu", rating="5.0", is_popular=True)
        Platform.objects.create(platform_type="BROKER", name="Hidden", is_active=False)
        response = self.client.get("/api/market-platforms/?platform_type=BROKER&ordering=-rating,sort_order&page_size=1")
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(response.data["results"][0]["id"], other.pk)
        self.assertIsNotNone(response.data["next"])
        self.assertEqual(self.client.get("/api/market-platforms/?search=Alpha").data["count"], 1)
        self.assertEqual(self.client.get("/api/market-platforms/?is_popular=true").data["count"], 1)
        self.assertEqual(self.client.get("/api/market-platforms/?ordering=bad").status_code, 400)
        self.assertEqual(self.client.get("/api/market-platforms/?page_size=999").data["count"], 3)
        self.assertEqual(self.client.get("/api/market-platforms/?platform_type=BROKER&search=Hidden").data["count"], 0)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get("/api/market-platforms/manage/?is_active=false").data["count"], 1)

    def test_compare_validation_and_order(self):
        second = Platform.objects.create(platform_type="BROKER", name="Second")
        third = Platform.objects.create(platform_type="BROKER", name="Third")
        self.client.force_authenticate(self.user)
        good = self.client.get(f"/api/market-platforms/compare/?ids={second.pk},{self.broker.pk}")
        self.assertEqual(good.status_code, 200)
        self.assertEqual([row["id"] for row in good.data["platforms"]], [second.pk, self.broker.pk])
        self.assertEqual(good.data["platform_type"], "BROKER")
        three = self.client.get(f"/api/market-platforms/compare/?ids={third.pk},{self.broker.pk},{second.pk}")
        self.assertEqual([row["id"] for row in three.data["platforms"]], [third.pk, self.broker.pk, second.pk])
        for ids in (str(self.broker.pk), f"{self.broker.pk},{self.broker.pk}",
                    f"{self.broker.pk},{self.exchange.pk}", "a,b", "1,2,3,4"):
            self.assertEqual(self.client.get(f"/api/market-platforms/compare/?ids={ids}").status_code, 400)
        self.assertEqual(self.client.get(f"/api/market-platforms/compare/?ids={self.broker.pk},999999").status_code, 404)

    def test_multipart_create_patch_logo_and_validation(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post("/api/market-platforms/manage/", {
            "platform_type": "BROKER", "name": "Real Platform", "rating": "4.5",
            "is_active": "true", "is_popular": "false", "sort_order": "0",
            "registration_url": "https://example.com/signup?ref=one&campaign=two",
            "details": '{"regulation":"Registered"}', "logo": logo_file(),
        }, format="multipart")
        self.assertEqual(response.status_code, 201, response.data)
        pk = response.data["id"]
        self.assertTrue(response.data["logo"].startswith("http"))
        self.assertEqual(response.data["registration_url"], "https://example.com/signup?ref=one&campaign=two")
        original_logo = Platform.objects.get(pk=pk).logo.name
        no_logo = self.client.patch(f"/api/market-platforms/manage/{pk}/", {"subtitle": "Updated"}, format="multipart")
        self.assertEqual(no_logo.status_code, 200, no_logo.data)
        self.assertEqual(Platform.objects.get(pk=pk).logo.name, original_logo)
        bad = self.client.patch(f"/api/market-platforms/manage/{pk}/", {
            "logo": SimpleUploadedFile("script.png", b"not an image", content_type="image/png"),
        }, format="multipart")
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(self.client.patch(f"/api/market-platforms/manage/{pk}/", {
            "logo": logo_file(), "remove_logo": "true",
        }, format="multipart").status_code, 400)
        self.assertEqual(self.client.patch(f"/api/market-platforms/manage/{pk}/", {
            "platform_type": "EXCHANGE",
        }, format="multipart").status_code, 400)
        self.assertEqual(self.client.patch(f"/api/market-platforms/manage/{pk}/", {
            "details": "not-json",
        }, format="multipart").status_code, 400)
        self.assertEqual(self.client.patch(f"/api/market-platforms/manage/{pk}/", {
            "details": '{"kyc":"Wrong type"}',
        }, format="multipart").status_code, 400)
        merged = self.client.patch(f"/api/market-platforms/manage/{pk}/", {
            "details": '{"pros":"Fast"}',
        }, format="multipart")
        self.assertEqual(merged.data["details"], {"regulation": "Registered", "pros": "Fast"})
        self.assertEqual(self.client.patch(f"/api/market-platforms/manage/{pk}/", {
            "registration_url": "https://person:secret@example.com/",
        }, format="multipart").status_code, 400)
        self.assertEqual(self.client.patch(f"/api/market-platforms/manage/{pk}/", {
            "rating": "0.5",
        }, format="multipart").status_code, 400)
        self.assertEqual(self.client.patch(f"/api/market-platforms/manage/{pk}/", {
            "sort_order": "-1",
        }, format="multipart").status_code, 400)
        self.assertEqual(self.client.patch(f"/api/market-platforms/manage/{pk}/", {
            "description": "x" * 10001,
        }, format="multipart").status_code, 400)
        removed = self.client.patch(f"/api/market-platforms/manage/{pk}/", {"remove_logo": "true"}, format="multipart")
        self.assertEqual(removed.status_code, 200, removed.data)
        self.assertIsNone(removed.data["logo"])
        self.assertGreaterEqual(PlatformChangeAudit.objects.filter(platform_id=pk).count(), 3)
        self.assertEqual(self.client.delete(f"/api/market-platforms/manage/{pk}/").status_code, 204)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get(f"/api/market-platforms/{pk}/").status_code, 404)

    def test_field_management_and_inactive_public_projection(self):
        self.client.force_authenticate(self.admin)
        field = FieldDefinition.objects.get(platform_type="BROKER", key="regulation")
        self.assertEqual(self.client.delete(f"/api/market-platforms/manage/fields/{field.pk}/").status_code, 409)
        self.assertEqual(self.client.patch(f"/api/market-platforms/manage/fields/{field.pk}/", {
            "is_active": False,
        }, format="json").status_code, 200)
        self.client.force_authenticate(self.user)
        public = self.client.get(f"/api/market-platforms/{self.broker.pk}/")
        self.assertNotIn("regulation", public.data["details"])
        self.assertEqual(self.client.get("/api/market-platforms/fields/?platform_type=BROKER").data["count"], 9)
        self.client.force_authenticate(self.admin)
        manage = self.client.get(f"/api/market-platforms/manage/{self.broker.pk}/")
        self.assertEqual(manage.data["details"]["regulation"], "A")
        self.assertEqual(self.client.get("/api/market-platforms/manage/fields/?platform_type=BROKER").data["count"], 10)
        self.assertEqual(self.client.post("/api/market-platforms/manage/fields/", {
            "platform_type": "BROKER", "key": "__proto__", "label": "Unsafe",
        }, format="json").status_code, 400)
        self.assertEqual(self.client.post("/api/market-platforms/manage/fields/", {
            "platform_type": "BROKER", "key": "regulation", "label": "Duplicate",
        }, format="json").status_code, 400)
        created = self.client.post("/api/market-platforms/manage/fields/", {
            "platform_type": "BROKER", "key": "new_field", "label": "New", "sort_order": 99,
        }, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(self.client.delete(f"/api/market-platforms/manage/fields/{created.data['id']}/").status_code, 204)
        self.assertTrue(PlatformChangeAudit.objects.filter(action="FIELD_DELETE").exists())

    def test_old_brokers_endpoint_remains(self):
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get("/api/brokers/").status_code, 200)
