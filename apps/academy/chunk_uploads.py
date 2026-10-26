"""Resumable course-session videos without a large CDN request body."""

import hashlib
import logging
import os
import shutil
import stat
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.parsers import BaseParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import CanTeachAcademy
from common.validators import ALLOWED_VIDEO_EXTENSIONS

from .models import AcademyVideoUpload
from .serializers import CourseSessionSerializer
from .views import manageable_courses


CHUNK_SIZE = 4 * 1024 * 1024
MAX_VIDEO_SIZE = 500 * 1024 * 1024
UPLOAD_LIFETIME = timedelta(hours=24)
MAX_ACTIVE_UPLOADS = 2
MIN_FREE_SPACE = 1024 * 1024 * 1024
logger = logging.getLogger(__name__)
VIDEO_CONTENT_TYPES = {
    ".mp4": "video/mp4", ".mov": "video/quicktime",
    ".webm": "video/webm", ".mkv": "video/x-matroska",
}


class UploadConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "UPLOAD_CONFLICT"


class UploadExpired(APIException):
    status_code = status.HTTP_410_GONE
    default_code = "UPLOAD_EXPIRED"


class UploadStorageUnavailable(APIException):
    status_code = 507
    default_code = "UPLOAD_STORAGE_UNAVAILABLE"


def staging_root():
    root = Path(settings.ACADEMY_UPLOAD_STAGING_ROOT)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.is_symlink() or not root.is_dir():
        raise RuntimeError("Academy upload staging directory is unsafe.")
    if root.resolve().is_relative_to(Path(settings.MEDIA_ROOT).resolve()):
        raise RuntimeError("Academy upload staging directory cannot be inside public media storage.")
    if os.name == "posix":
        info = root.stat()
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise RuntimeError("Academy upload staging directory must be owned by the service and mode 0700.")
    return root


def staging_path(upload):
    # The database UUID, never a client filename, determines the private path.
    return staging_root() / upload.id.hex


def remove_staging_file(upload):
    staging_path(upload).unlink(missing_ok=True)


def upload_payload(upload):
    return {
        "upload_id": str(upload.pk),
        "status": upload.status,
        "offset": upload.received_size,
        "size": upload.expected_size,
        "chunk_size": CHUNK_SIZE,
        "expires_at": upload.expires_at,
        "session_id": upload.session_id,
    }


class UploadStartSerializer(serializers.Serializer):
    filename = serializers.CharField(max_length=200)
    size = serializers.IntegerField(min_value=1, max_value=MAX_VIDEO_SIZE)
    sha256 = serializers.RegexField(r"^[0-9a-fA-F]{64}$", required=False, allow_blank=True)
    client_upload_id = serializers.UUIDField(required=False)

    def validate_filename(self, value):
        if value != Path(value.replace("\\", "/")).name or any(ord(ch) < 32 for ch in value):
            raise serializers.ValidationError("Use a filename without a path or control characters.")
        if Path(value).suffix.lower() not in ALLOWED_VIDEO_EXTENSIONS:
            raise serializers.ValidationError("Only MP4, MOV, WebM and MKV videos are accepted.")
        return value


class VideoChunkParser(BaseParser):
    media_type = "application/octet-stream"

    def parse(self, stream, media_type=None, parser_context=None):
        data = stream.read(CHUNK_SIZE + 1)
        if not data or len(data) > CHUNK_SIZE:
            raise ValidationError({"chunk": "Chunk must contain 1 to 4194304 bytes."})
        return data


class UploadBaseView(APIView):
    permission_classes = [IsAuthenticated, CanTeachAcademy]

    def get_course(self):
        if not hasattr(self, "_course"):
            self._course = get_object_or_404(manageable_courses(self.request.user), slug=self.kwargs["slug"])
        return self._course

    def get_upload(self, *, lock=False):
        queryset = AcademyVideoUpload.objects
        if lock:
            queryset = queryset.select_for_update()
        return get_object_or_404(
            queryset, pk=self.kwargs["upload_id"],
            course=self.get_course(), user=self.request.user,
        )

    @staticmethod
    def assert_pending(upload):
        if upload.status != AcademyVideoUpload.Status.PENDING:
            raise UploadConflict({"code": "UPLOAD_NOT_PENDING", "detail": "Upload is no longer pending."})
        if upload.expires_at <= timezone.now():
            raise UploadExpired({"code": "UPLOAD_EXPIRED", "detail": "Upload expired; start a new upload."})


class VideoUploadStartView(UploadBaseView):
    parser_classes = [JSONParser]

    def post(self, request, slug):
        course = self.get_course()
        incoming = UploadStartSerializer(data=request.data)
        incoming.is_valid(raise_exception=True)
        with transaction.atomic():
            # Serialize quota checks for concurrent starts by this account.
            type(request.user).objects.select_for_update().get(pk=request.user.pk)
            client_upload_id = incoming.validated_data.get("client_upload_id")
            if client_upload_id:
                previous = AcademyVideoUpload.objects.filter(
                    user=request.user, client_upload_id=client_upload_id,
                ).first()
                if previous:
                    same_upload = (
                        previous.course_id == course.pk
                        and previous.filename == incoming.validated_data["filename"]
                        and previous.expected_size == incoming.validated_data["size"]
                        and previous.expected_sha256 == incoming.validated_data.get("sha256", "").lower()
                    )
                    if not same_upload:
                        raise UploadConflict({"code": "IDEMPOTENCY_CONFLICT", "detail": "This client_upload_id belongs to another file."})
                    return Response(upload_payload(previous))
            active = AcademyVideoUpload.objects.filter(
                user=request.user, status=AcademyVideoUpload.Status.PENDING,
                expires_at__gt=timezone.now(),
            ).count()
            if active >= MAX_ACTIVE_UPLOADS:
                raise UploadConflict({"code": "UPLOAD_LIMIT", "detail": "Finish or cancel an active upload first."})
            upload = AcademyVideoUpload.objects.create(
                course=course, user=request.user,
                filename=incoming.validated_data["filename"],
                expected_size=incoming.validated_data["size"],
                expected_sha256=incoming.validated_data.get("sha256", "").lower(),
                client_upload_id=client_upload_id,
                expires_at=timezone.now() + UPLOAD_LIFETIME,
            )
        return Response(upload_payload(upload), status=status.HTTP_201_CREATED)


class VideoUploadStateView(UploadBaseView):
    def get(self, request, slug, upload_id):
        return Response(upload_payload(self.get_upload()))

    def delete(self, request, slug, upload_id):
        with transaction.atomic():
            upload = self.get_upload(lock=True)
            self.assert_pending(upload)
            upload.status = AcademyVideoUpload.Status.CANCELLED
            upload.save(update_fields=["status", "updated_at"])
        try:
            remove_staging_file(upload)
        except OSError:
            logger.warning("academy_upload_staging_cleanup_failed upload_id=%s", upload.pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


class VideoUploadChunkView(UploadBaseView):
    parser_classes = [VideoChunkParser]

    def put(self, request, slug, upload_id):
        try:
            offset = int(request.headers.get("X-Upload-Offset", ""))
        except ValueError as exc:
            raise ValidationError({"offset": "X-Upload-Offset must be an integer."}) from exc
        if offset < 0:
            raise ValidationError({"offset": "Offset cannot be negative."})
        chunk = request.data
        with transaction.atomic():
            upload = self.get_upload(lock=True)
            self.assert_pending(upload)
            path = staging_path(upload)
            if offset > upload.received_size or offset + len(chunk) > upload.expected_size:
                raise UploadConflict({"code": "OFFSET_MISMATCH", "offset": upload.received_size})
            if offset < upload.received_size and offset + len(chunk) > upload.received_size:
                raise UploadConflict({"code": "OFFSET_MISMATCH", "offset": upload.received_size})
            if offset == upload.received_size and len(chunk) != CHUNK_SIZE and offset + len(chunk) != upload.expected_size:
                raise ValidationError({"chunk": "Only the final chunk may be shorter than chunk_size."})
            if offset == upload.received_size and shutil.disk_usage(staging_root()).free < len(chunk) + MIN_FREE_SPACE:
                raise UploadStorageUnavailable({"code": "UPLOAD_STORAGE_UNAVAILABLE", "detail": "Video staging storage is full."})

            flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
            if upload.received_size == 0 and not path.exists():
                flags |= os.O_CREAT | os.O_EXCL
            try:
                descriptor = os.open(path, flags, 0o600)
            except FileNotFoundError as exc:
                raise UploadConflict({"code": "UPLOAD_FILE_MISSING", "detail": "Start a new upload."}) from exc
            with os.fdopen(descriptor, "r+b") as file:
                actual_size = os.fstat(file.fileno()).st_size
                if actual_size < upload.received_size:
                    raise UploadConflict({"code": "UPLOAD_FILE_MISSING", "detail": "Start a new upload."})
                if actual_size > upload.received_size:
                    file.truncate(upload.received_size)  # Recover an uncommitted interrupted write.
                file.seek(offset)
                if offset < upload.received_size:
                    if file.read(len(chunk)) != chunk:
                        raise UploadConflict({"code": "CHUNK_MISMATCH", "offset": upload.received_size})
                else:
                    try:
                        file.write(chunk)
                        file.flush()
                        os.fsync(file.fileno())
                    except OSError:
                        file.truncate(upload.received_size)
                        raise
                    upload.received_size += len(chunk)
                    upload.save(update_fields=["received_size", "updated_at"])
        return Response(upload_payload(upload))


class VideoUploadCompleteView(UploadBaseView):
    parser_classes = [JSONParser, MultiPartParser]

    def post(self, request, slug, upload_id):
        course = self.get_course()
        with transaction.atomic():
            upload = self.get_upload(lock=True)
            if upload.status == AcademyVideoUpload.Status.COMPLETED and upload.session_id:
                return Response(CourseSessionSerializer(upload.session, context={"request": request}).data)
            self.assert_pending(upload)
            if upload.received_size != upload.expected_size:
                raise UploadConflict({"code": "UPLOAD_INCOMPLETE", "offset": upload.received_size})
            path = staging_path(upload)
            if not path.is_file() or path.stat().st_size != upload.expected_size:
                raise UploadConflict({"code": "UPLOAD_FILE_MISSING", "detail": "Start a new upload."})
            if "video_file" in request.data or "audio_file" in request.data:
                raise ValidationError({"video_file": "Video is supplied by the completed upload only."})
            if upload.expected_sha256:
                digest = hashlib.sha256()
                with path.open("rb") as file:
                    for block in iter(lambda: file.read(1024 * 1024), b""):
                        digest.update(block)
                if digest.hexdigest() != upload.expected_sha256:
                    raise UploadConflict({"code": "CHECKSUM_MISMATCH", "detail": "Uploaded video differs from the original."})
            data = request.data.copy()
            with path.open("rb") as source:
                extension = Path(upload.filename).suffix.lower()
                video = File(source, name=f"{upload.id.hex}{extension}")
                video.content_type = VIDEO_CONTENT_TYPES[extension]
                data["video_file"] = video
                serializer = CourseSessionSerializer(data=data, context={"request": request, "view": self})
                serializer.is_valid(raise_exception=True)
                session = serializer.save(course=course)
            upload.session = session
            upload.status = AcademyVideoUpload.Status.COMPLETED
            upload.save(update_fields=["session", "status", "updated_at"])
        try:
            remove_staging_file(upload)
        except OSError:
            logger.warning("academy_upload_staging_cleanup_failed upload_id=%s", upload.pk)
        return Response(CourseSessionSerializer(session, context={"request": request}).data, status=status.HTTP_201_CREATED)
