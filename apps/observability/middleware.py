import time
import uuid

from django.conf import settings

from apps.activity.services import ActivityService

from .models import LogEvent
from .services import ObservabilityService


class ObservabilityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started = time.monotonic()
        request_id = request.headers.get("X-Request-ID", "")[:64] or uuid.uuid4().hex
        request.observability_request_id = request_id
        try:
            response = self.get_response(request)
        except Exception as exc:
            ObservabilityService.record_exception(request, exc, request_id=request_id)
            request._observability_logged = True
            raise

        duration_ms = max(0, int((time.monotonic() - started) * 1000))
        response["X-Request-ID"] = request_id
        status_code = getattr(response, "status_code", 200)
        slow_ms = getattr(settings, "OBSERVABILITY_SLOW_REQUEST_MS", 2000)
        should_log = status_code >= 400 or duration_ms >= slow_ms
        if should_log and not getattr(request, "_observability_logged", False):
            user = getattr(request, "user", None)
            if not getattr(user, "is_authenticated", False):
                user = None
            level = LogEvent.Level.ERROR if status_code >= 500 else LogEvent.Level.WARNING
            category = "http_error" if status_code >= 400 else "slow_request"
            ObservabilityService.record(
                source=LogEvent.Source.BACKEND,
                level=level,
                category=category,
                message=f"{request.method} {request.path} returned {status_code}",
                request_id=request_id,
                method=request.method,
                path=request.path[:1000],
                status_code=status_code,
                duration_ms=duration_ms,
                user=user,
                ip_address=ActivityService.client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
            )
        return response
