import django_filters

from .models import LiveEvent


class LiveEventFilter(django_filters.FilterSet):

    starts_after = (
        django_filters.IsoDateTimeFilter(
            field_name="starts_at",
            lookup_expr="gte",
        )
    )

    starts_before = (
        django_filters.IsoDateTimeFilter(
            field_name="starts_at",
            lookup_expr="lte",
        )
    )

    class Meta:
        model = LiveEvent

        fields = (
            "status",
            "host",
            "is_active",
            "starts_after",
            "starts_before",
        )