from django_filters import rest_framework as filters

from .models import Message


class MessageFilter(filters.FilterSet):

    sender = filters.NumberFilter(
        field_name="sender_id",
    )

    sender_username = filters.CharFilter(
        field_name="sender__username",
        lookup_expr="iexact",
    )

    is_deleted = filters.BooleanFilter()

    has_attachment = filters.BooleanFilter(
        method="filter_has_attachment",
    )

    created_after = filters.IsoDateTimeFilter(
        field_name="created_at",
        lookup_expr="gte",
    )

    created_before = filters.IsoDateTimeFilter(
        field_name="created_at",
        lookup_expr="lte",
    )

    class Meta:
        model = Message

        fields = (
            "sender",
            "sender_username",
            "is_deleted",
            "has_attachment",
            "created_after",
            "created_before",
        )

    def filter_has_attachment(
        self,
        queryset,
        name,
        value,
    ):
        if value is True:
            return queryset.exclude(
                attachment=""
            ).exclude(
                attachment__isnull=True
            )

        if value is False:
            return queryset.filter(
                attachment=""
            ) | queryset.filter(
                attachment__isnull=True
            )

        return queryset