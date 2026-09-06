import logging
import traceback


class DatabaseLogHandler(logging.Handler):
    """Best-effort persistence for server warnings/errors; never raises."""

    def emit(self, record):
        if record.name.startswith(("django.db.backends", "apps.observability")):
            return
        try:
            from .models import LogEvent
            from .services import ObservabilityService

            level = record.levelname.lower()
            if level not in {"warning", "error", "critical"}:
                level = "warning"
            stack = ""
            if record.exc_info:
                stack = "".join(traceback.format_exception(*record.exc_info))
            ObservabilityService.record(
                source=LogEvent.Source.BACKEND,
                level=level,
                category="python_log",
                message=record.getMessage(),
                error_type=record.exc_info[0].__name__ if record.exc_info else "",
                stack_trace=stack,
                context={"logger": record.name, "module": record.module},
            )
        except Exception:
            return
