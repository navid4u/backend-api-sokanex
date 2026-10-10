from io import BytesIO
import os
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.academy.models import Course, CourseSession


def png_file(name="image.png"):
    buffer = BytesIO()
    Image.new("RGB", (2, 2), "red").save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


def video_file(name="lesson.mp4"):
    return SimpleUploadedFile(name, b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00", content_type="video/mp4")


class AcademyMultipartUploadTests(APITestCase):
    def setUp(self):
        self.media_dir = TemporaryDirectory()
        self.addCleanup(self.media_dir.cleanup)
        override = override_settings(MEDIA_ROOT=self.media_dir.name)
        override.enable()
        self.addCleanup(override.disable)
        self.teacher = User.objects.create_user(username="upload-teacher", role=User.Role.ADMIN)
        self.normal = User.objects.create_user(username="upload-normal")
        self.client.force_authenticate(self.teacher)

    def test_course_and_session_real_multipart_create_and_patch(self):
        course_response = self.client.post("/api/academy/courses/", {
            "title": "Multipart course", "description": "Lessons", "cover_image": png_file(),
            "allowed_levels": [1, 3], "estimated_duration_minutes": "",
            "starts_at": "2026-10-10T10:00:00+03:30",
        }, format="multipart")
        self.assertEqual(course_response.status_code, 201, course_response.data)
        course = Course.objects.get(pk=course_response.data["id"])
        self.assertEqual(course.allowed_levels, [1, 3])
        self.assertIsNone(course.estimated_duration_minutes)
        self.assertTrue(course.cover_image.storage.exists(course.cover_image.name))
        self.assertTrue(course_response.data["cover_image"].startswith("http://testserver/media/"))

        course_patch = self.client.patch(f"/api/academy/courses/{course.slug}/", {
            "cover_image": png_file("new.png"), "weekly_session_limit": "",
        }, format="multipart")
        self.assertEqual(course_patch.status_code, 200, course_patch.data)
        course.refresh_from_db()
        self.assertIn("new.png", course.cover_image.name)

        session_response = self.client.post(f"/api/academy/courses/{course.slug}/sessions/", {
            "title": "Video lesson", "order": 1, "video_url": "", "video_file": video_file(),
            "image": png_file("session.png"), "duration_minutes": "",
        }, format="multipart")
        self.assertEqual(session_response.status_code, 201, session_response.data)
        session = CourseSession.objects.get(pk=session_response.data["id"])
        self.assertEqual(session.video_url, "")
        self.assertIsNone(session.duration_minutes)
        self.assertTrue(session.video_file.storage.exists(session.video_file.name))
        self.assertTrue(session_response.data["video_file"].startswith("http://testserver/media/"))
        self.assertTrue(session_response.data["image"].startswith("http://testserver/media/"))
        old_name = session.video_file.name
        no_file_patch = self.client.patch(f"/api/academy/sessions/{session.pk}/", {
            "title": "Updated lesson",
        }, format="multipart")
        self.assertEqual(no_file_patch.status_code, 200, no_file_patch.data)
        session.refresh_from_db()
        self.assertEqual(session.video_file.name, old_name)
        new_file_patch = self.client.patch(f"/api/academy/sessions/{session.pk}/", {
            "video_url": "", "video_file": video_file("replacement.mp4"),
        }, format="multipart")
        self.assertEqual(new_file_patch.status_code, 200, new_file_patch.data)
        session.refresh_from_db()
        self.assertIn("replacement.mp4", session.video_file.name)
        self.assertEqual(session.video_url, "")
        get_response = self.client.get(f"/api/academy/sessions/{session.pk}/")
        self.assertEqual(get_response.status_code, 200, get_response.data)
        self.assertTrue(get_response.data["video_file"].startswith("http://testserver/media/"))

    def test_invalid_file_and_permission(self):
        bad = self.client.post("/api/academy/courses/", {
            "title": "Bad", "cover_image": SimpleUploadedFile("fake.txt", b"text", content_type="text/plain"),
        }, format="multipart")
        self.assertEqual(bad.status_code, 400)
        self.client.force_authenticate(self.normal)
        denied = self.client.post("/api/academy/courses/", {"title": "Denied"}, format="multipart")
        self.assertEqual(denied.status_code, 403)

    def test_disguised_video_is_rejected(self):
        course = Course.objects.create(title="Video validation", instructor=self.teacher)
        result = self.client.post(f"/api/academy/courses/{course.slug}/sessions/", {
            "title": "Bad media", "order": 1,
            "video_file": SimpleUploadedFile("fake.mp4", b"not a video", content_type="video/mp4"),
        }, format="multipart")
        self.assertEqual(result.status_code, 400)
        self.assertIn("video_file", result.data["errors"])
        self.assertFalse(CourseSession.objects.filter(course=course).exists())

    def test_oversize_image_returns_readable_validation_not_server_error(self):
        buffer = BytesIO()
        Image.frombytes("RGB", (1800, 1800), os.urandom(1800 * 1800 * 3)).save(buffer, format="PNG")
        oversized = SimpleUploadedFile("huge.png", buffer.getvalue(), content_type="image/png")
        self.assertGreater(oversized.size, 8 * 1024 * 1024)
        result = self.client.post("/api/academy/courses/", {
            "title": "Oversized", "cover_image": oversized,
        }, format="multipart")
        self.assertEqual(result.status_code, 400)
        self.assertIn("cover_image", result.data["errors"])
        self.assertIn("cannot exceed 8 MB", str(result.data["errors"]["cover_image"]))
        self.assertFalse(Course.objects.filter(title="Oversized").exists())
