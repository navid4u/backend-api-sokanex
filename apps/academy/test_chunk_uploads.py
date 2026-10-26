import hashlib
import uuid
from tempfile import TemporaryDirectory
from datetime import timedelta

from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.academy.chunk_uploads import CHUNK_SIZE, staging_path
from apps.academy.models import AcademyVideoUpload, Course, CourseSession
from apps.academy.test_multipart_uploads import png_file


VIDEO = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00"


class AcademyChunkUploadTests(APITestCase):
    def setUp(self):
        self.private = TemporaryDirectory()
        self.media = TemporaryDirectory()
        self.addCleanup(self.private.cleanup)
        self.addCleanup(self.media.cleanup)
        override = override_settings(
            ACADEMY_UPLOAD_STAGING_ROOT=self.private.name,
            MEDIA_ROOT=self.media.name,
        )
        override.enable()
        self.addCleanup(override.disable)
        self.teacher = User.objects.create_user(username="chunk-teacher", role=User.Role.ADMIN)
        self.stranger = User.objects.create_user(username="chunk-stranger")
        self.other_teacher = User.objects.create_user(username="chunk-other", role=User.Role.ADMIN)
        self.course = Course.objects.create(title="Chunk course", instructor=self.teacher)
        self.other_course = Course.objects.create(title="Other course", instructor=self.other_teacher)
        self.client.force_authenticate(self.teacher)
        self.root = f"/api/academy/courses/{self.course.slug}/session-video-uploads/"

    def start(self, content=VIDEO, sha256=""):
        response = self.client.post(self.root, {
            "filename": "session.mp4", "size": len(content), "sha256": sha256,
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data["upload_id"]

    def chunk(self, upload_id, content, offset=0):
        return self.client.put(
            f"{self.root}{upload_id}/chunk/", content,
            content_type="application/octet-stream", HTTP_X_UPLOAD_OFFSET=str(offset),
        )

    def complete(self, upload_id, **fields):
        return self.client.post(
            f"{self.root}{upload_id}/complete/",
            {"title": "Chunk session", "order": 1, "video_url": "", **fields},
            format="json",
        )

    def test_upload_resume_retry_create_once_and_keep_legacy_route(self):
        content = VIDEO + b"x" * (CHUNK_SIZE - len(VIDEO)) + b"tail"
        upload_id = self.start(content, hashlib.sha256(content).hexdigest())
        upload = AcademyVideoUpload.objects.get(pk=upload_id)
        self.assertFalse(str(staging_path(upload)).startswith(self.media.name))

        first = self.chunk(upload_id, content[:CHUNK_SIZE])
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(first.data["offset"], CHUNK_SIZE)
        again = self.chunk(upload_id, content[:CHUNK_SIZE])
        self.assertEqual(again.status_code, 200, again.data)
        status = self.client.get(f"{self.root}{upload_id}/")
        self.assertEqual(status.data["offset"], CHUNK_SIZE)
        self.assertFalse(CourseSession.objects.exists())

        last = self.chunk(upload_id, content[CHUNK_SIZE:], CHUNK_SIZE)
        self.assertEqual(last.status_code, 200, last.data)
        created = self.complete(upload_id)
        self.assertEqual(created.status_code, 201, created.data)
        session = CourseSession.objects.get(pk=created.data["id"])
        with session.video_file.open("rb") as file:
            self.assertEqual(file.read(), content)
        self.assertFalse(staging_path(upload).exists())
        retry = self.complete(upload_id)
        self.assertEqual(retry.status_code, 200, retry.data)
        self.assertEqual(retry.data["id"], session.pk)
        self.assertEqual(CourseSession.objects.count(), 1)

    def test_incomplete_invalid_and_wrong_hash_never_publish(self):
        incomplete_content = VIDEO + b"x" * (CHUNK_SIZE - len(VIDEO)) + b"tail"
        upload_id = self.start(incomplete_content)
        self.assertEqual(self.complete(upload_id).status_code, 409)
        self.assertEqual(self.chunk(upload_id, incomplete_content[:CHUNK_SIZE]).status_code, 200)
        bad = self.complete(upload_id)
        self.assertEqual(bad.status_code, 409)  # Remaining bytes are missing.
        self.assertFalse(CourseSession.objects.exists())
        self.assertEqual(self.client.delete(f"{self.root}{upload_id}/").status_code, 204)

        upload_id = self.start(b"not a video")
        self.assertEqual(self.chunk(upload_id, b"not a video").status_code, 200)
        invalid = self.complete(upload_id)
        self.assertEqual(invalid.status_code, 400)
        self.assertFalse(CourseSession.objects.exists())
        self.assertEqual(self.client.delete(f"{self.root}{upload_id}/").status_code, 204)

        upload_id = self.start(VIDEO, "0" * 64)
        self.assertEqual(self.chunk(upload_id, VIDEO).status_code, 200)
        mismatch = self.complete(upload_id)
        self.assertEqual(mismatch.status_code, 409)
        self.assertFalse(CourseSession.objects.exists())

    def test_permissions_offsets_expiry_cleanup_and_cors(self):
        upload_id = self.start(VIDEO)
        self.client.force_authenticate(self.stranger)
        self.assertEqual(self.client.get(f"{self.root}{upload_id}/").status_code, 403)
        self.assertEqual(self.chunk(upload_id, VIDEO).status_code, 403)
        self.client.force_authenticate(self.other_teacher)
        self.assertEqual(self.client.get(f"{self.root}{upload_id}/").status_code, 404)
        self.client.force_authenticate(self.teacher)

        bad_offset = self.chunk(upload_id, VIDEO, 4)
        self.assertEqual(bad_offset.status_code, 409)
        self.assertEqual(self.chunk(upload_id, VIDEO).status_code, 200)
        conflicting_retry = self.chunk(upload_id, b"x" * len(VIDEO))
        self.assertEqual(conflicting_retry.status_code, 409)
        cors = self.client.options(
            f"{self.root}{upload_id}/chunk/",
            HTTP_ORIGIN="https://app.sokanex.com",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="PUT",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization,content-type,x-upload-offset",
        )
        self.assertEqual(cors.status_code, 200)
        self.assertIn("x-upload-offset", cors["Access-Control-Allow-Headers"])

        upload = AcademyVideoUpload.objects.get(pk=upload_id)
        AcademyVideoUpload.objects.filter(pk=upload_id).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.complete(upload_id).status_code, 410)
        call_command("cleanup_academy_video_uploads")
        upload.refresh_from_db()
        self.assertEqual(upload.status, AcademyVideoUpload.Status.EXPIRED)
        self.assertFalse(staging_path(upload).exists())

    def test_cancel_and_no_cross_course_access(self):
        upload_id = self.start(VIDEO)
        self.assertEqual(self.client.get(
            f"/api/academy/courses/{self.other_course.slug}/session-video-uploads/{upload_id}/"
        ).status_code, 404)
        self.assertEqual(self.client.delete(f"{self.root}{upload_id}/").status_code, 204)
        self.assertEqual(self.chunk(upload_id, VIDEO).status_code, 409)

    def test_limits_and_invalid_filename(self):
        invalid = self.client.post(self.root, {"filename": "../bad.mp4", "size": 10}, format="json")
        self.assertEqual(invalid.status_code, 400)
        huge = self.client.post(self.root, {"filename": "a.mp4", "size": 500 * 1024 * 1024 + 1}, format="json")
        self.assertEqual(huge.status_code, 400)
        self.start(VIDEO)
        self.start(VIDEO)
        third = self.client.post(self.root, {"filename": "a.mp4", "size": 10}, format="json")
        self.assertEqual(third.status_code, 409)

    def test_start_idempotency_and_oversized_chunk(self):
        key = str(uuid.uuid4())
        payload = {"filename": "lesson.mp4", "size": len(VIDEO), "client_upload_id": key}
        first = self.client.post(self.root, payload, format="json")
        self.assertEqual(first.status_code, 201, first.data)
        again = self.client.post(self.root, payload, format="json")
        self.assertEqual(again.status_code, 200, again.data)
        self.assertEqual(first.data["upload_id"], again.data["upload_id"])
        conflict = self.client.post(self.root, {**payload, "size": len(VIDEO) + 1}, format="json")
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(AcademyVideoUpload.objects.count(), 1)
        too_large = self.chunk(first.data["upload_id"], b"x" * (CHUNK_SIZE + 1))
        self.assertEqual(too_large.status_code, 400)

    def test_complete_with_multipart_image_and_existing_session_validation(self):
        upload_id = self.start(VIDEO)
        self.assertEqual(self.chunk(upload_id, VIDEO).status_code, 200)
        invalid = self.client.post(f"{self.root}{upload_id}/complete/", {
            "title": "With image", "order": 1, "video_url": "https://example.org/video",
            "image": png_file(),
        }, format="multipart")
        self.assertEqual(invalid.status_code, 400)
        self.assertFalse(CourseSession.objects.exists())

        good = self.client.post(f"{self.root}{upload_id}/complete/", {
            "title": "With image", "order": 1, "video_url": "",
            "image": png_file(), "is_published": "true",
        }, format="multipart")
        self.assertEqual(good.status_code, 201, good.data)
        session = CourseSession.objects.get(pk=good.data["id"])
        self.assertTrue(session.image.storage.exists(session.image.name))
        self.assertTrue(session.video_file.storage.exists(session.video_file.name))
