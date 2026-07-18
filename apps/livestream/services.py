from django.db.models import Q
from django.utils import timezone

from .models import LiveEvent


class LiveEventService:

    @staticmethod
    def public_events():
        return (
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

    @staticmethod
    def all_events():
        return LiveEvent.objects.select_related(
            "host",
            "created_by",
        )

    @staticmethod
    def live_now():
        now = timezone.now()

        return (
            LiveEventService.public_events()
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
    def upcoming():
        return (
            LiveEventService.public_events()
            .filter(
                status=LiveEvent.Status.SCHEDULED,
                starts_at__gte=timezone.now(),
            )
        )