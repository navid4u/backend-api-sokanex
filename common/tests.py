from types import SimpleNamespace

from django.test import SimpleTestCase
from rest_framework import serializers

from .validators import (
    validate_attachment_upload,
    validate_image_upload,
    validate_video_upload,
)


class UploadValidatorTests(SimpleTestCase):
    def create_file(
        self,
        *,
        name,
        content_type,
        size=1024,
    ):
        return SimpleNamespace(
            name=name,
            content_type=content_type,
            size=size,
        )

    def test_valid_image_is_accepted(self):
        uploaded_file = self.create_file(
            name="avatar.webp",
            content_type="image/webp",
        )

        result = validate_image_upload(
            uploaded_file,
            max_size_mb=5,
        )

        self.assertIs(
            result,
            uploaded_file,
        )

    def test_executable_image_extension_is_rejected(
        self
    ):
        uploaded_file = self.create_file(
            name="avatar.exe",
            content_type="image/jpeg",
        )

        with self.assertRaises(
            serializers.ValidationError
        ):
            validate_image_upload(
                uploaded_file,
                max_size_mb=5,
            )

    def test_invalid_image_content_type_is_rejected(
        self
    ):
        uploaded_file = self.create_file(
            name="avatar.jpg",
            content_type=(
                "application/x-msdownload"
            ),
        )

        with self.assertRaises(
            serializers.ValidationError
        ):
            validate_image_upload(
                uploaded_file,
                max_size_mb=5,
            )

    def test_oversized_image_is_rejected(self):
        uploaded_file = self.create_file(
            name="large.jpg",
            content_type="image/jpeg",
            size=(
                5 * 1024 * 1024
                + 1
            ),
        )

        with self.assertRaises(
            serializers.ValidationError
        ):
            validate_image_upload(
                uploaded_file,
                max_size_mb=5,
            )

    def test_valid_video_is_accepted(self):
        uploaded_file = self.create_file(
            name="training.mp4",
            content_type="video/mp4",
        )

        result = validate_video_upload(
            uploaded_file,
        )

        self.assertIs(
            result,
            uploaded_file,
        )

    def test_executable_attachment_is_rejected(
        self
    ):
        uploaded_file = self.create_file(
            name="malware.exe",
            content_type=(
                "application/x-msdownload"
            ),
        )

        with self.assertRaises(
            serializers.ValidationError
        ):
            validate_attachment_upload(
                uploaded_file
            )