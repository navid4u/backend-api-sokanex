"""Private storage for new social post media; never expose storage URLs."""

from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateSocialStorage(FileSystemStorage):
    def __init__(self):
        super().__init__(directory_permissions_mode=0o700, file_permissions_mode=0o600)

    @property
    def base_location(self):
        return str(getattr(
            settings, "SOCIAL_PRIVATE_MEDIA_ROOT",
            Path(settings.BASE_DIR).parent / "private-social-media",
        ))

    @property
    def location(self):
        return str(Path(self.base_location).resolve())

    @property
    def base_url(self):
        return None


private_social_storage = PrivateSocialStorage()
