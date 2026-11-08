import tempfile
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase
from PIL import Image

from apps.accounts.models import User

from .models import SavedPost, TraderPost, UserFollow


@override_settings(SOCIAL_PRIVATE_MEDIA_ROOT=tempfile.mkdtemp(), MEDIA_ROOT=tempfile.mkdtemp())
class SocialPrivacyTests(APITestCase):
    def setUp(self):
        self.author = User.objects.create_user(username="09120000001", first_name="Ali", last_name="Trader")
        self.viewer = User.objects.create_user(username="social-viewer")
        self.other = User.objects.create_user(username="social-other")
        self.client.force_authenticate(self.author)

    def test_multipart_video_and_authorized_range_without_public_storage_url(self):
        video = SimpleUploadedFile("clip.mp4", b"0123456789", content_type="video/mp4")
        response = self.client.post("/api/chat/social/feed/", {
            "video": video, "visibility": "FOLLOWERS",
        }, format="multipart")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["text"], "")
        self.assertNotIn("/media/social/", response.data["video"])
        self.assertNotIn("09120000001", str(response.data))
        post = TraderPost.objects.get(pk=response.data["id"])
        self.assertTrue(post.video.storage.exists(post.video.name))
        path = f"/api/chat/social/posts/{post.pk}/media/video/"
        own = self.client.get(path, HTTP_RANGE="bytes=2-5")
        self.assertEqual(own.status_code, 206)
        self.assertEqual(b"".join(own.streaming_content), b"2345")
        self.assertEqual(own["Content-Range"], "bytes 2-5/10")
        self.client.force_authenticate(self.viewer)
        self.assertEqual(self.client.get(path).status_code, 404)
        UserFollow.objects.create(follower=self.viewer, following=self.author)
        allowed = self.client.get(path)
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(b"".join(allowed.streaming_content), b"0123456789")
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(path).status_code, 401)

    def test_public_social_payload_and_search_hide_phone_username(self):
        response = self.client.post("/api/chat/social/feed/", {"text": "hello"}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["author"]["display_name"], "Ali Trader")
        self.assertNotIn("username", response.data["author"])
        self.client.force_authenticate(self.viewer)
        for path in (
            "/api/chat/social/feed/",
            f"/api/chat/social/users/{self.author.pk}/",
            "/api/chat/social/users/top-contributors/",
        ):
            self.assertNotIn("09120000001", str(self.client.get(path).data))
        self.assertEqual(len(self.client.get("/api/chat/social/feed/?search=09120000001").data["results"]), 0)

    def test_image_upload_and_invalid_media_are_reported_as_json(self):
        image_bytes = BytesIO()
        Image.new("RGB", (1, 1), "red").save(image_bytes, format="PNG")
        image = SimpleUploadedFile("cover.png", image_bytes.getvalue(), content_type="image/png")
        created = self.client.post("/api/chat/social/feed/", {
            "image": image, "visibility": "PRIVATE",
        }, format="multipart", HTTP_HOST="api.sokanex.com")
        self.assertEqual(created.status_code, 201)
        self.assertTrue(created.data["image"].startswith("https://api.sokanex.com/"))
        self.assertIn(f"/social/posts/{created.data['id']}/media/image/", created.data["image"])
        self.client.force_authenticate(self.viewer)
        self.assertEqual(self.client.get(created.data["image"]).status_code, 404)
        self.client.force_authenticate(self.author)
        bad = SimpleUploadedFile("not-video.exe", b"bad", content_type="application/octet-stream")
        response = self.client.post("/api/chat/social/feed/", {"video": bad}, format="multipart")
        self.assertEqual(response.status_code, 400)
        self.assertIn("video", response.data["errors"])

    def test_soft_deleted_post_disappears_from_feed_profile_saved_and_media(self):
        response = self.client.post("/api/chat/social/feed/", {"text": "temporary"}, format="json")
        post_id = response.data["id"]
        SavedPost.objects.create(user=self.viewer, post_id=post_id)
        self.assertEqual(self.client.delete(f"/api/chat/social/posts/{post_id}/").status_code, 204)
        self.assertTrue(TraderPost.objects.get(pk=post_id).is_deleted)
        self.client.force_authenticate(self.viewer)
        self.assertEqual(self.client.get("/api/chat/social/feed/").data["results"], [])
        self.assertEqual(self.client.get(f"/api/chat/social/users/{self.author.pk}/posts/").data["results"], [])
        self.assertEqual(self.client.get("/api/chat/social/saved/").data["results"], [])
        self.assertEqual(self.client.get(f"/api/chat/social/posts/{post_id}/media/video/").status_code, 404)

    def test_moderator_can_delete_private_post_without_becoming_a_viewer(self):
        private = TraderPost.objects.create(author=self.author, text="private", visibility="PRIVATE")
        self.client.force_authenticate(self.viewer)
        self.assertEqual(self.client.delete(f"/api/chat/social/posts/{private.pk}/").status_code, 404)
        moderator = User.objects.create_user(username="social-mod", role=User.Role.SUPER_ADMIN)
        self.client.force_authenticate(moderator)
        self.assertEqual(self.client.delete(f"/api/chat/social/posts/{private.pk}/").status_code, 204)
        self.assertTrue(TraderPost.objects.get(pk=private.pk).is_deleted)
