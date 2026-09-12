import hashlib
import secrets

from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import APIException, AuthenticationFailed

from apps.accounts.models import User


class IngestionNotConfigured(APIException):
    status_code = 503
    default_detail = "Content ingestion is not configured."
    default_code = "ingestion_not_configured"


class FixedIngestionKeyAuthentication(BaseAuthentication):
    header = "HTTP_X_SOKANEX_INGEST_KEY"

    def authenticate_header(self, request):
        return "X-Sokanex-Ingest-Key"

    def authenticate(self, request):
        configured_key = settings.CONTENT_INGESTION_API_KEY
        if not configured_key:
            raise IngestionNotConfigured()
        supplied_key = request.META.get(self.header, "")
        if not supplied_key or not secrets.compare_digest(supplied_key, configured_key):
            raise AuthenticationFailed("Invalid ingestion API key.")
        try:
            user = User.objects.get(username=settings.CONTENT_INGESTION_AUTHOR_USERNAME)
        except User.DoesNotExist as exc:
            raise IngestionNotConfigured("Content ingestion author is missing.") from exc
        fingerprint = hashlib.sha256(configured_key.encode()).hexdigest()[:12]
        return user, f"ingestion-key:{fingerprint}"
