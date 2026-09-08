import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import (
    exception_handler,
)


logger = logging.getLogger(
    "django.request"
)


def custom_exception_handler(
    exc,
    context,
):
    response = exception_handler(
        exc,
        context,
    )

    if response is None:
        request = context.get("request")
        view = context.get("view")

        request_method = getattr(
            request,
            "method",
            "UNKNOWN",
        )
        request_path = getattr(
            request,
            "path",
            "UNKNOWN",
        )
        view_name = (
            view.__class__.__name__
            if view
            else "UnknownView"
        )

        logger.error(
            (
                "Unhandled API exception: "
                "method=%s path=%s view=%s"
            ),
            request_method,
            request_path,
            view_name,
            exc_info=(
                type(exc),
                exc,
                exc.__traceback__,
            ),
        )

        try:
            from apps.observability.services import ObservabilityService
            ObservabilityService.record_exception(
                request,
                exc,
                request_id=getattr(request, "observability_request_id", ""),
            )
            request._observability_logged = True
        except Exception:
            pass

        return Response(
            {
                "success": False,
                "message": (
                    "Internal Server Error"
                ),
                "errors": {},
            },
            status=(
                status
                .HTTP_500_INTERNAL_SERVER_ERROR
            ),
        )

    payload = {
        "success": False,
        "message": getattr(exc, "public_message", "Request Failed"),
        "errors": response.data,
    }
    machine_code = getattr(exc, "machine_code", None)
    if machine_code:
        payload["error_code"] = machine_code
    extra_payload = getattr(exc, "extra_payload", None)
    if extra_payload:
        payload.update(extra_payload)

    request = context.get("request")
    request_path = getattr(request, "path", "")
    expected_user_input_error = request_path.startswith("/api/accounts/auth/otp/")

    if response.status_code == status.HTTP_400_BAD_REQUEST and not expected_user_input_error:
        try:
            from apps.observability.models import LogEvent
            from apps.observability.services import ObservabilityService

            user = getattr(request, "user", None)
            if not getattr(user, "is_authenticated", False):
                user = None
            ObservabilityService.record(
                source=LogEvent.Source.BACKEND,
                level=LogEvent.Level.WARNING,
                category="validation_error",
                message=f"{getattr(request, 'method', '')} {getattr(request, 'path', '')} failed validation",
                request_id=getattr(request, "observability_request_id", ""),
                method=getattr(request, "method", ""),
                path=getattr(request, "path", "")[:1000],
                status_code=response.status_code,
                user=user,
                context={"validation_errors": response.data},
            )
            request._observability_logged = True
            underlying_request = getattr(request, "_request", None)
            if underlying_request is not None:
                underlying_request._observability_logged = True
        except Exception:
            pass

    return Response(
        payload,
        status=response.status_code,
        headers=response.headers,
    )
