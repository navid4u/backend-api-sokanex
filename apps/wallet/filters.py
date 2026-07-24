from django_filters import rest_framework as filters

from .models import Transaction


class TransactionFilter(filters.FilterSet):

    transaction_type = filters.ChoiceFilter(
        choices=Transaction.Type.choices,
    )

    status = filters.ChoiceFilter(
        choices=Transaction.Status.choices,
    )

    min_amount = filters.NumberFilter(
        field_name="amount",
        lookup_expr="gte",
    )

    max_amount = filters.NumberFilter(
        field_name="amount",
        lookup_expr="lte",
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
        model = Transaction

        fields = (
            "transaction_type",
            "status",
            "min_amount",
            "max_amount",
            "created_after",
            "created_before",
        )