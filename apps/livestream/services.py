from django.db.models import Q
from django.utils import timezone

from .models import LiveEvent
from .models import AlocomSettings
from common.content_access import restrict_queryset_for_user
import json
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


class LiveEventService:

    @staticmethod
    def public_events(user=None):
        queryset = (
            LiveEvent.objects.filter(
                is_active=True
            )
            .exclude(
                status=LiveEvent.Status.CANCELLED
            )
            .select_related(
                "host",
                "created_by",
            )
        )
        if user is not None:
            queryset = restrict_queryset_for_user(queryset, user)
        return queryset

    @staticmethod
    def all_events():
        return LiveEvent.objects.select_related(
            "host",
            "created_by",
        )

    @staticmethod
    def live_now(user=None):
        now = timezone.now()

        return (
            LiveEventService.public_events(user)
            .filter(
                status=LiveEvent.Status.LIVE,
                starts_at__lte=now,
            )
            .filter(
                Q(ends_at__isnull=True)
                | Q(ends_at__gte=now)
            )
        )

    @staticmethod
    def upcoming(user=None):
        return (
            LiveEventService.public_events(user)
            .filter(
                status=LiveEvent.Status.SCHEDULED,
                starts_at__gte=timezone.now(),
            )
        )


class AlocomClientError(Exception):
    pass


class AlocomClient:
    """Low-level client. Resource paths come from Alocom's OpenAPI contract."""

    def __init__(self, integration=None):
        self.integration = integration or AlocomSettings.load()

    def request(self, method, path, payload=None):
        if not self.integration.enabled:
            raise AlocomClientError("Alocom integration is disabled.")
        token = self.integration.get_api_token()
        if not token:
            raise AlocomClientError("Alocom API token is not configured.")
        url = urljoin(self.integration.api_base_url.rstrip("/") + "/", path.lstrip("/"))
        body = json.dumps(payload).encode() if payload is not None else None
        request = Request(
            url,
            data=body,
            method=method.upper(),
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json", "Content-Type": "application/json"},
        )
        context = None if self.integration.verify_ssl else ssl._create_unverified_context()
        try:
            with urlopen(request, timeout=self.integration.request_timeout_seconds, context=context) as response:
                content = response.read()
                return json.loads(content.decode()) if content else {}
        except HTTPError as exc:
            raise AlocomClientError(f"Alocom returned HTTP {exc.code}.") from exc
        except (URLError, TimeoutError, ValueError) as exc:
            raise AlocomClientError("Could not communicate with Alocom.") from exc
