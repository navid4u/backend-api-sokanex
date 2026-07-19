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

    return Response(
        {
            "success": False,
            "message": "Request Failed",
            "errors": response.data,
        },
        status=response.status_code,
        headers=response.headers,
    )