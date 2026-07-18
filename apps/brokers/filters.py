import django_filters

from .models import Broker


class BrokerFilter(django_filters.FilterSet):

    min_rating = django_filters.NumberFilter(
        field_name="rating",
        lookup_expr="gte",
    )

    max_minimum_deposit = (
        django_filters.NumberFilter(
            field_name="minimum_deposit",
            lookup_expr="lte",
        )
    )

    class Meta:
        model = Broker

        fields = (
            "country",
            "is_active",
            "min_rating",
            "max_minimum_deposit",
        )