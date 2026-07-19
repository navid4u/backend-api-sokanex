from django.db import (
    DatabaseError,
    connection,
)
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import (
    require_GET,
)


@require_GET
def home(request):
    return JsonResponse(
        {
            "status": "ok",
            "project": "Trading Platform API",
            "version": "1.0.0",
        }
    )


@require_GET
def health_check(request):
    database_status = "healthy"
    http_status = 200

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()

    except DatabaseError:
        database_status = "unhealthy"
        http_status = 503

    service_status = (
        "healthy"
        if http_status == 200
        else "unhealthy"
    )

    return JsonResponse(
        {
            "status": service_status,
            "service": "trading-platform-api",
            "version": "1.0.0",
            "database": database_status,
            "timestamp": (
                timezone.now().isoformat()
            ),
        },
        status=http_status,
    )