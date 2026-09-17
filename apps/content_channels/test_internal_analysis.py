import tempfile
import base64
from datetime import timedelta

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import PlatformRole, User
from .models import Channel, ChannelPost


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class InternalAnalysisAPITests(APITestCase):
    def setUp(self):
        cache.clear()
        self.channel = Channel.objects.get(slug="internal-analysis")
        self.user = User.objects.create_user(username="analysis-user", password="StrongPass123!")
        self.manager_role = PlatformRole.objects.create(
            name="Analysis Manager", slug="analysis-manager",
            permissions=[User.Permission.INTERNAL_ANALYSIS_MANAGE],
        )
        self.manager = User.objects.create_user(
            username="analysis-manager", password="StrongPass123!", custom_role=self.manager_role
        )
        self.admin = User.objects.create_superuser(
            username="analysis-admin", password="StrongPass123!", email="analysis@example.com"
        )
        self.list_url = reverse("internal-analysis-channel")
        self.manage_url = reverse("internal-analysis-manage")

    def authenticate(self, user):
        self.client.force_authenticate(user)

    def create_post(self, **kwargs):
        defaults = {
            "channel": self.channel, "title": "Gold outlook", "body": "Analysis body",
            "scope": ChannelPost.Scope.GOLD, "status": ChannelPost.Status.PUBLISHED,
            "author": self.admin, "published_at": timezone.now(),
        }
        defaults.update(kwargs)
        return ChannelPost.objects.create(**defaults)

    def test_public_list_only_contains_due_published_posts_and_orders_pinned_first(self):
        visible = self.create_post(title="Visible")
        pinned = self.create_post(title="Pinned", is_pinned=True)
        self.create_post(title="Draft", status=ChannelPost.Status.DRAFT)
        self.create_post(
            title="Future", status=ChannelPost.Status.PUBLISHED,
            published_at=timezone.now() + timedelta(days=1),
        )
        self.authenticate(self.user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([row["id"] for row in response.data["results"]], [pinned.id, visible.id])
        self.assertEqual(response.data["results"][0]["scope"], "GOLD")
        self.assertIn("author_name", response.data["results"][0])
        self.assertIn("scope_display", response.data["results"][0])

    def test_public_scope_filter_and_pagination(self):
        self.create_post(scope=ChannelPost.Scope.GOLD)
        stock = self.create_post(scope=ChannelPost.Scope.STOCK)
        self.authenticate(self.user)
        response = self.client.get(self.list_url, {"scope": "STOCK", "page_size": 1})
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], stock.id)

    def test_regular_user_cannot_manage_but_custom_permission_can(self):
        self.authenticate(self.user)
        self.assertEqual(self.client.get(self.manage_url).status_code, status.HTTP_403_FORBIDDEN)
        self.authenticate(self.manager)
        self.assertEqual(self.client.get(self.manage_url).status_code, status.HTTP_200_OK)

    def test_management_crud_and_filters(self):
        self.authenticate(self.manager)
        create = self.client.post(self.manage_url, {
            "title": "Dollar report", "body": "Body", "scope": "DOLLAR",
            "status": "PUBLISHED", "is_pinned": True,
        }, format="json")
        self.assertEqual(create.status_code, status.HTTP_201_CREATED)
        post_id = create.data["id"]
        filtered = self.client.get(self.manage_url, {
            "status": "PUBLISHED", "scope": "DOLLAR", "is_pinned": "true", "search": "Dollar"
        })
        self.assertEqual(filtered.data["count"], 1)
        detail_url = reverse("internal-analysis-manage-detail", args=[post_id])
        patch = self.client.patch(detail_url, {"title": "Updated report"}, format="json")
        self.assertEqual(patch.status_code, status.HTTP_200_OK)
        put = self.client.put(detail_url, {
            "title": "Replaced", "body": "New body", "scope": "GOLD", "status": "DRAFT"
        }, format="json")
        self.assertEqual(put.status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.delete(detail_url).status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(ChannelPost.objects.filter(pk=post_id).exists())

    def test_legacy_create_and_public_response_have_empty_opportunity_details(self):
        self.authenticate(self.manager)
        response = self.client.post(self.manage_url, {
            "title": "Legacy compatible", "body": "Body", "scope": "GOLD",
            "status": "PUBLISHED",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["external_url"], "")
        self.assertEqual(response.data["more_info_text"], "")
        self.assertIsNone(response.data["more_info_video"])
        self.assertEqual(response.data["usage_guide_text"], "")
        self.assertIsNone(response.data["usage_guide_video"])

    def test_multipart_create_and_partial_patch_preserve_detail_videos(self):
        self.authenticate(self.manager)
        response = self.client.post(self.manage_url, {
            "title": "Opportunity", "body": "Body", "scope": "GOLD",
            "status": "PUBLISHED", "external_url": "https://example.com/opportunity",
            "more_info_text": "<b>More</b>", "usage_guide_text": "<script>x</script>Guide",
            "more_info_video": SimpleUploadedFile(
                "more.mp4", b"more-video", content_type="video/mp4"
            ),
            "usage_guide_video": SimpleUploadedFile(
                "guide.webm", b"guide-video", content_type="video/webm"
            ),
        }, format="multipart", secure=True)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["external_url"], "https://example.com/opportunity")
        self.assertEqual(response.data["more_info_text"], "More")
        self.assertEqual(response.data["usage_guide_text"], "xGuide")
        self.assertTrue(response.data["more_info_video"].startswith("https://"))
        self.assertTrue(response.data["usage_guide_video"].startswith("https://"))

        post = ChannelPost.objects.get(pk=response.data["id"])
        original_more = post.more_info_video.name
        original_guide = post.usage_guide_video.name
        detail_url = reverse("internal-analysis-manage-detail", args=[post.pk])
        patched = self.client.patch(
            detail_url, {"more_info_text": "Updated only"}, format="multipart", secure=True
        )
        self.assertEqual(patched.status_code, status.HTTP_200_OK, patched.data)
        post.refresh_from_db()
        self.assertEqual(post.more_info_text, "Updated only")
        self.assertEqual(post.more_info_video.name, original_more)
        self.assertEqual(post.usage_guide_video.name, original_guide)

    @override_settings(INTERNAL_ANALYSIS_DETAIL_VIDEO_MAX_MB=1)
    def test_detail_video_validation_is_field_level(self):
        self.authenticate(self.manager)
        invalid_mime = self.client.post(self.manage_url, {
            "title": "Invalid", "body": "Body", "scope": "GOLD", "status": "PUBLISHED",
            "more_info_video": SimpleUploadedFile(
                "bad.mp4", b"not-video", content_type="application/octet-stream"
            ),
        }, format="multipart")
        self.assertEqual(invalid_mime.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("more_info_video", invalid_mime.data)

        oversized = self.client.post(self.manage_url, {
            "title": "Large", "body": "Body", "scope": "GOLD", "status": "PUBLISHED",
            "usage_guide_video": SimpleUploadedFile(
                "large.mov", b"x" * (1024 * 1024 + 1), content_type="video/quicktime"
            ),
        }, format="multipart")
        self.assertEqual(oversized.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("usage_guide_video", oversized.data)

    def test_invalid_external_url_scheme_is_rejected(self):
        self.authenticate(self.manager)
        response = self.client.post(self.manage_url, {
            "title": "Bad URL", "body": "Body", "scope": "GOLD",
            "status": "PUBLISHED", "external_url": "ftp://example.com/file",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("external_url", response.data)

    def test_scheduled_validation_and_command(self):
        self.authenticate(self.manager)
        invalid = self.client.post(self.manage_url, {
            "title": "Bad schedule", "body": "Body", "scope": "GOLD", "status": "SCHEDULED"
        }, format="json")
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)
        due = self.create_post(
            status=ChannelPost.Status.SCHEDULED,
            published_at=timezone.now() - timedelta(minutes=1),
        )
        call_command("publish_scheduled_analysis")
        due.refresh_from_db()
        self.assertEqual(due.status, ChannelPost.Status.PUBLISHED)

    def test_upload_and_record_deletion_remove_owned_file(self):
        self.authenticate(self.manager)
        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        image = SimpleUploadedFile("analysis.png", png, content_type="image/png")
        response = self.client.post(self.manage_url, {
            "title": "Media post", "body": "Body", "scope": "GOLD",
            "status": "PUBLISHED", "image": image,
        }, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        post = ChannelPost.objects.get(pk=response.data["id"])
        storage, name = post.image.storage, post.image.name
        self.assertTrue(storage.exists(name))
        with self.captureOnCommitCallbacks(execute=True):
            deleted = self.client.delete(reverse("internal-analysis-manage-detail", args=[post.pk]))
        self.assertEqual(deleted.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(storage.exists(name))

    def test_view_count_is_atomic_and_deduplicated(self):
        post = self.create_post()
        self.authenticate(self.user)
        url = reverse("internal-analysis-view", args=[post.pk])
        first = self.client.post(url)
        second = self.client.post(url)
        self.assertTrue(first.data["counted"])
        self.assertFalse(second.data["counted"])
        post.refresh_from_db()
        self.assertEqual(post.views_count, 1)

    def test_user_response_exposes_internal_analysis_capability(self):
        self.authenticate(self.manager)
        response = self.client.get(reverse("profile"))
        self.assertTrue(response.data["capabilities"]["can_manage_internal_analysis"])
