from pathlib import Path

from rest_framework import serializers


ALLOWED_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
}

ALLOWED_IMAGE_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}


ALLOWED_VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".webm",
    ".mkv",
}

ALLOWED_VIDEO_CONTENT_TYPES = {
    "video/mp4",
    "video/quicktime",
    "video/webm",
    "video/x-matroska",
}


ALLOWED_ATTACHMENT_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".pdf",
    ".txt",
    ".csv",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".zip",
    ".mp4",
    ".mov",
    ".webm",
}

ALLOWED_ATTACHMENT_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf",
    "text/plain",
    "text/csv",
    "application/zip",
    "application/x-zip-compressed",
    "application/msword",
    (
        "application/vnd.openxmlformats-"
        "officedocument.wordprocessingml."
        "document"
    ),
    "application/vnd.ms-excel",
    (
        "application/vnd.openxmlformats-"
        "officedocument.spreadsheetml."
        "sheet"
    ),
    "video/mp4",
    "video/quicktime",
    "video/webm",
}


def validate_uploaded_file(
    uploaded_file,
    *,
    max_size,
    allowed_extensions,
    allowed_content_types,
    file_label="File",
):
    if not uploaded_file:
        return uploaded_file

    if uploaded_file.size > max_size:
        max_size_mb = (
            max_size / (1024 * 1024)
        )

        raise serializers.ValidationError(
            (
                f"{file_label} size cannot "
                f"exceed {max_size_mb:g} MB."
            )
        )

    filename = getattr(
        uploaded_file,
        "name",
        "",
    )

    extension = Path(
        filename
    ).suffix.lower()

    if extension not in allowed_extensions:
        allowed_values = ", ".join(
            sorted(allowed_extensions)
        )

        raise serializers.ValidationError(
            (
                f"Invalid {file_label.lower()} "
                f"extension. Allowed extensions: "
                f"{allowed_values}."
            )
        )

    content_type = getattr(
        uploaded_file,
        "content_type",
        "",
    )

    content_type = (
        content_type
        .split(";")[0]
        .strip()
        .lower()
    )

    if (
        content_type
        not in allowed_content_types
    ):
        raise serializers.ValidationError(
            (
                f"Invalid {file_label.lower()} "
                "content type."
            )
        )

    return uploaded_file


def validate_image_upload(
    uploaded_file,
    *,
    max_size_mb,
    file_label="Image",
):
    return validate_uploaded_file(
        uploaded_file,
        max_size=(
            max_size_mb
            * 1024
            * 1024
        ),
        allowed_extensions=(
            ALLOWED_IMAGE_EXTENSIONS
        ),
        allowed_content_types=(
            ALLOWED_IMAGE_CONTENT_TYPES
        ),
        file_label=file_label,
    )


def validate_video_upload(
    uploaded_file,
    *,
    max_size_mb=500,
    file_label="Video",
):
    return validate_uploaded_file(
        uploaded_file,
        max_size=(
            max_size_mb
            * 1024
            * 1024
        ),
        allowed_extensions=(
            ALLOWED_VIDEO_EXTENSIONS
        ),
        allowed_content_types=(
            ALLOWED_VIDEO_CONTENT_TYPES
        ),
        file_label=file_label,
    )


def validate_attachment_upload(
    uploaded_file,
    *,
    max_size_mb=20,
    file_label="Attachment",
):
    return validate_uploaded_file(
        uploaded_file,
        max_size=(
            max_size_mb
            * 1024
            * 1024
        ),
        allowed_extensions=(
            ALLOWED_ATTACHMENT_EXTENSIONS
        ),
        allowed_content_types=(
            ALLOWED_ATTACHMENT_CONTENT_TYPES
        ),
        file_label=file_label,
    )