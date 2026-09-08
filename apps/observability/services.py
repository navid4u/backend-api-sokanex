import re
import traceback

from django.conf import settings
from django.db import DatabaseError, OperationalError, ProgrammingError

from apps.activity.services import ActivityService

from .models import LogEvent


SENSITIVE_KEY = re.compile(
    r"(authorization|cookie|password|passwd|secret|token|api[_-]?key|otp|refresh|access|(?:verification|recovery)[_-]?code)",
    re.IGNORECASE,
)


def sanitize(value, depth=0):
    if depth > 4:
        return "[MAX_DEPTH]"
    if isinstance(value, dict):
        return {
            str(key)[:100]: "[REDACTED]" if SENSITIVE_KEY.search(str(key)) else sanitize(item, depth + 1)
            for key, item in list(value.items())[:50]
        }
    if isinstance(value, (list, tuple)):
        return [sanitize(item, depth + 1) for item in list(value)[:50]]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return SENSITIVE_KEY.sub("[REDACTED]", str(value))[:2000]


class ObservabilityService:
    @staticmethod
    def record(**fields):
        if not getattr(settings, "OBSERVABILITY_ENABLED", True):
            return None
        try:
            fields["context"] = sanitize(fields.get("context") or {})
            fields["message"] = str(fields.get("message") or "Unknown error")[:1000]
            fields["stack_trace"] = str(fields.get("stack_trace") or "")[:16000]
            client_event_id = fields.get("client_event_id")
            if fields.get("source") == LogEvent.Source.FRONTEND and client_event_id:
                event, _ = LogEvent.objects.get_or_create(
                    source=LogEvent.Source.FRONTEND,
                    client_event_id=client_event_id,
                    defaults={key: value for key, value in fields.items() if key not in {"source", "client_event_id"}},
                )
                return event
            return LogEvent.objects.create(**fields)
        except (DatabaseError, OperationalError, ProgrammingError, ValueError, TypeError):
            # Observability must never change application behavior.
            return None

    @classmethod
    def record_exception(cls, request, exc, *, status_code=500, request_id=""):
        user = getattr(request, "user", None)
        if not getattr(user, "is_authenticated", False):
            user = None
        return cls.record(
            source=LogEvent.Source.BACKEND,
            level=LogEvent.Level.CRITICAL if status_code >= 500 else LogEvent.Level.ERROR,
            category="unhandled_exception",
            message=str(exc) or exc.__class__.__name__,
            error_type=f"{exc.__class__.__module__}.{exc.__class__.__name__}",
            stack_trace="".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
            request_id=request_id,
            method=getattr(request, "method", ""),
            path=getattr(request, "path", "")[:1000],
            status_code=status_code,
            user=user,
            ip_address=ActivityService.client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
        )
