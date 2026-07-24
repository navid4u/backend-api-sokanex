import tempfile
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.videos.models import Video, VideoCategory


class VideoAPITests(APITestCase):

    def setUp(self):
        self.media_directory = (
            tempfile.TemporaryDirectory()
        )

        self.media_override = override_settings(
            MEDIA_ROOT=self.media_directory.name
        )

        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.addCleanup(
            self.media_directory.cleanup
        )

        password = "StrongPass123!"

        self.user = User.objects.create_user(
            username="customer",
            password=password,
            role=User.Role.USER,
        )

        self.trader = User.objects.create_user(
            username="trader",
            password=password,
            role=User.Role.TRADER,
        )

        self.employee = User.objects.create_user(
            username="employee",
            password=password,
            role=User.Role.EMPLOYEE,
        )

        self.category = (
            VideoCategory.objects.create(
                name="Trading videos"
            )
        )

        self.published_video = (
            Video.objects.create(
                title="Published video",
                summary="Published summary",
                source_type=(
                    Video.SourceType.EXTERNAL
                ),
                external_url=(
                    "https://example.com/"
                    "published-video"
                ),
                category=self.category,
                author=self.employee,
                status=Video.Status.PUBLISHED,
                published_at=timezone.now(),
            )
        )

        self.draft_video = Video.objects.create(
            title="Draft video",
            summary="Draft summary",
            source_type=Video.SourceType.EXTERNAL,
            external_url=(
                "https://example.com/draft-video"
            ),
            category=self.category,
            author=self.employee,
            status=Video.Status.DRAFT,
        )

        self.future_video = Video.objects.create(
            title="Future video",
            summary="Future summary",
            source_type=Video.SourceType.EXTERNAL,
            external_url=(
                "https://example.com/future-video"
            ),
            category=self.category,
            author=self.employee,
            status=Video.Status.PUBLISHED,
            published_at=(
                timezone.now()
                + timedelta(days=1)
            ),
        )

    def authenticate(self, user):
        self.client.force_authenticate(
            user=user
        )

    def external_payload(
        self,
        status_value=Video.Status.DRAFT,
    ):
        return {
            "title": "External course",
            "summary": "Course summary",
            "source_type": (
                Video.SourceType.EXTERNAL
            ),
            "external_url": (
                "https://example.com/course"
            ),
            "category": self.category.pk,
            "duration_seconds": 600,
            "status": status_value,
        }

    def uploaded_file(self):
        return SimpleUploadedFile(
            "lesson.mp4",
            b"fake video content",
            content_type="video/mp4",
        )

    def test_list_requires_authentication(self):
        response = self.client.get(
            reverse("video-list-create")
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_user_only_sees_published_videos(
        self
    ):
        self.authenticate(self.user)

        response = self.client.get(
            reverse("video-list-create")
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        returned_ids = {
            item["id"]
            for item in response.data["results"]
        }

        self.assertIn(
            self.published_video.id,
            returned_ids,
        )

        self.assertNotIn(
            self.draft_video.id,
            returned_ids,
        )

        self.assertNotIn(
            self.future_video.id,
            returned_ids,
        )

    def test_user_cannot_open_draft(self):
        self.authenticate(self.user)

        response = self.client.get(
            reverse(
                "video-detail",
                kwargs={
                    "slug": self.draft_video.slug
                },
            )
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_user_and_trader_cannot_create(
        self
    ):
        for actor in (
            self.user,
            self.trader,
        ):
            self.authenticate(actor)

            response = self.client.post(
                reverse("video-list-create"),
                self.external_payload(),
                format="json",
            )

            self.assertEqual(
                response.status_code,
                status.HTTP_403_FORBIDDEN,
            )

    def test_employee_can_create_external_video(
        self
    ):
        self.authenticate(self.employee)

        response = self.client.post(
            reverse("video-list-create"),
            self.external_payload(
                Video.Status.PUBLISHED
            ),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        video = Video.objects.get(
            pk=response.data["id"]
        )

        self.assertEqual(
            video.author,
            self.employee,
        )

        self.assertEqual(
            video.status,
            Video.Status.PUBLISHED,
        )

        self.assertIsNotNone(
            video.published_at
        )

    def test_external_video_requires_url(self):
        self.authenticate(self.employee)

        payload = self.external_payload()
        payload["external_url"] = ""

        response = self.client.post(
            reverse("video-list-create"),
            payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertIn(
            "external_url",
            response.data["errors"],
        )

    def test_uploaded_video_requires_file(self):
        self.authenticate(self.employee)

        payload = self.external_payload()
        payload["source_type"] = (
            Video.SourceType.UPLOAD
        )
        payload["external_url"] = ""

        response = self.client.post(
            reverse("video-list-create"),
            payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertIn(
            "video_file",
            response.data["errors"],
        )

    def test_employee_can_upload_video(self):
        self.authenticate(self.employee)

        response = self.client.post(
            reverse("video-list-create"),
            {
                "title": "Uploaded lesson",
                "summary": "Uploaded summary",
                "source_type": (
                    Video.SourceType.UPLOAD
                ),
                "video_file": self.uploaded_file(),
                "external_url": "",
                "category": self.category.pk,
                "status": Video.Status.DRAFT,
            },
            format="multipart",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        video = Video.objects.get(
            pk=response.data["id"]
        )

        self.assertEqual(
            video.source_type,
            Video.SourceType.UPLOAD,
        )

        self.assertTrue(
            bool(video.video_file)
        )

    def test_management_list_includes_drafts(
        self
    ):
        self.authenticate(self.employee)

        response = self.client.get(
            reverse("video-management-list")
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        returned_ids = {
            item["id"]
            for item in response.data["results"]
        }

        self.assertIn(
            self.published_video.id,
            returned_ids,
        )

        self.assertIn(
            self.draft_video.id,
            returned_ids,
        )

    def test_employee_can_publish_draft(self):
        self.authenticate(self.employee)

        response = self.client.patch(
            reverse(
                "video-detail",
                kwargs={
                    "slug": self.draft_video.slug
                },
            ),
            {
                "status": Video.Status.PUBLISHED,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.draft_video.refresh_from_db()

        self.assertEqual(
            self.draft_video.status,
            Video.Status.PUBLISHED,
        )

        self.assertIsNotNone(
            self.draft_video.published_at
        )

    def test_category_permissions(self):
        url = reverse(
            "video-category-list-create"
        )

        self.authenticate(self.user)

        response = self.client.post(
            url,
            {
                "name": "Forbidden category",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.authenticate(self.employee)

        response = self.client.post(
            url,
            {
                "name": "Market analysis",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

    def test_delete_permissions(self):
        detail_url = reverse(
            "video-detail",
            kwargs={
                "slug": self.published_video.slug
            },
        )

        self.authenticate(self.user)

        response = self.client.delete(
            detail_url
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.authenticate(self.employee)

        response = self.client.delete(
            detail_url
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_204_NO_CONTENT,
        )

        self.assertFalse(
            Video.objects.filter(
                pk=self.published_video.pk
            ).exists()
        )
        
    def test_user_cannot_update_video_category(
        self
     ):
        self.authenticate(self.user)

        response = self.client.patch(
            reverse(
                "video-category-detail",
                kwargs={
                    "pk": self.category.pk,
                },
            ),
            {
                "name": "Updated category",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.category.refresh_from_db()

        self.assertEqual(
            self.category.name,
            "Trading videos",
        )

    def test_employee_can_update_video_category(
        self
    ):
        self.authenticate(self.employee)

        response = self.client.patch(
            reverse(
                "video-category-detail",
                kwargs={
                    "pk": self.category.pk,
                },
            ),
            {
                "name": "Updated category",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.category.refresh_from_db()

        self.assertEqual(
            self.category.name,
            "Updated category",
        )

    def test_user_cannot_delete_video_category(
        self
    ):
        self.authenticate(self.user)

        response = self.client.delete(
            reverse(
                "video-category-detail",
                kwargs={
                    "pk": self.category.pk,
                },
            )
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.assertTrue(
            VideoCategory.objects.filter(
                pk=self.category.pk
            ).exists()
        )

    def test_employee_can_delete_video_category(
        self
    ):
        self.authenticate(self.employee)

        response = self.client.delete(
            reverse(
                "video-category-detail",
                kwargs={
                    "pk": self.category.pk,
                },
            )
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_204_NO_CONTENT,
        )

        self.assertFalse(
            VideoCategory.objects.filter(
                pk=self.category.pk
            ).exists()
        )

        self.published_video.refresh_from_db()

        self.assertIsNone(
            self.published_video.category
        )