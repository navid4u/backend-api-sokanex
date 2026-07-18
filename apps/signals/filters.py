import django_filters

from .models import Signal


class SignalFilter(django_filters.FilterSet):

    created_by = django_filters.NumberFilter(
        field_name="created_by_id",
    )

    created_after = django_filters.DateFilter(
        field_name="created_at__date",
        lookup_expr="gte",
    )

    created_before = django_filters.DateFilter(
        field_name="created_at__date",
        lookup_expr="lte",
    )

    class Meta:
        model = Signal

        fields = [
            "market",
            "status",
            "direction",
            "created_by",
            "created_after",
            "created_before",
        ]