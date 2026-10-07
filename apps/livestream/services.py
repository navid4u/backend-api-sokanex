from .models import LiveEvent
from apps.accounts.content_section_access import restrict_content_section_queryset
from apps.accounts.models import ContentSectionAccessPolicy


class LiveEventService:

    @staticmethod
    def public_events(user=None):
        queryset = (
            LiveEvent.objects.filter(
                is_active=True
            )
            .select_related(
                "host",
                "created_by",
            )
            .order_by("-starts_at", "-id")
        )
        if user is not None:
            queryset = restrict_content_section_queryset(queryset, user, ContentSectionAccessPolicy.Section.LIVESTREAMS)
        return queryset

    @staticmethod
    def all_events():
        return LiveEvent.objects.select_related(
            "host",
            "created_by",
        ).order_by("-starts_at", "-id")

    @staticmethod
    def live_now(user=None):
        return LiveEventService.public_events(user).filter(status=LiveEvent.Status.ACTIVE)

    @staticmethod
    def upcoming(user=None):
        return LiveEventService.public_events(user).filter(
            status__in=[LiveEvent.Status.UPCOMING, LiveEvent.Status.WITHIN_HOUR]
        )
