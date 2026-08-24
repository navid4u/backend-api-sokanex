from django.db.models import Q
from django.utils import timezone

from .models import LiveEvent
from common.content_access import restrict_queryset_for_user


class LiveEventService:

    @staticmethod
    def public_events(user=None):
        queryset = (
            LiveEvent.objects.filter(
                is_active=True
            )
            .exclude(
                status__in=[LiveEvent.Status.CANCELLED, LiveEvent.Status.DISABLED]
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
                starts_at__gte=timezone.now(),
            )
        )
