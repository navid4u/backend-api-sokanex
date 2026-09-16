import base64
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.accounts.models import User

from .models import ManualSignalPost


PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class ManualSignalPostAPITests(APITestCase):
    url = "/api/signals/manual-posts/"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media = tempfile.TemporaryDirectory()
        cls._media_override = override_settings(MEDIA_ROOT=cls._media.name)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        cls._media.cleanup()
        super().tearDownClass()

    def setUp(self):
        self.superadmin = User.objects.create_superuser(
            username="manual-post-admin", password="Pass123!"
        )
        self.user = User.objects.create_user(username="manual-post-user", password="Pass123!")

    def image(self, *, name="valid.png", content=PNG_BYTES, content_type="image/png"):
        return SimpleUploadedFile(name, content, content_type=content_type)

    def test_authenticated_user_can_list_only_active_posts_newest_first(self):
        old = ManualSignalPost.objects.create(author=self.superadmin, text="قدیمی")
        inactive = ManualSignalPost.objects.create(author=self.superadmin, text="مخفی", is_active=False)
        newest = ManualSignalPost.objects.create(author=self.superadmin, text="جدید")
        self.client.force_authenticate(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual([item["id"] for item in response.data["results"]], [newest.id, old.id])
        self.assertNotIn(inactive.id, [item["id"] for item in response.data["results"]])

    def test_list_requires_authentication(self):
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_superadmin_can_create_text_only_post_and_html_is_removed(self):
        self.client.force_authenticate(self.superadmin)
        response = self.client.post(self.url, {"text": "<script>alert(1)</script><b>تحلیل</b>"}, format="multipart")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["kind"], "MANUAL_POST")
        self.assertEqual(response.data["source"], "SUPER_ADMIN_MANUAL")
        self.assertNotIn("<", response.data["text"])
        self.assertEqual(ManualSignalPost.objects.get().author, self.superadmin)

    def test_superadmin_can_create_image_only_post_with_random_name(self):
        self.client.force_authenticate(self.superadmin)
        response = self.client.post(self.url, {"image": self.image()}, format="multipart")

        self.assertEqual(response.status_code, 201)
        post = ManualSignalPost.objects.get()
        self.assertTrue(post.image.name.startswith("signals/manual/"))
        self.assertNotIn("valid.png", post.image.name)
        self.assertTrue(response.data["image"].startswith("http"))

    def test_regular_user_cannot_create(self):
        self.client.force_authenticate(self.user)
        self.assertEqual(
            self.client.post(self.url, {"text": "مطلب"}, format="multipart").status_code,
            403,
        )

    def test_empty_payload_is_rejected(self):
        self.client.force_authenticate(self.superadmin)
        self.assertEqual(self.client.post(self.url, {}, format="multipart").status_code, 400)

    def test_non_image_file_is_rejected(self):
        self.client.force_authenticate(self.superadmin)
        bad = self.image(name="attack.png", content=b"not an image", content_type="image/png")
        self.assertEqual(self.client.post(self.url, {"image": bad}, format="multipart").status_code, 400)

    def test_author_and_source_cannot_be_spoofed(self):
        self.client.force_authenticate(self.superadmin)
        response = self.client.post(
            self.url,
            {"text": "مطلب", "author": self.user.pk, "source": "TELEGRAM_API"},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ManualSignalPost.objects.count(), 0)
