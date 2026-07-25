import django_filters

from .models import User


class UserFilter(django_filters.FilterSet):

    class Meta:

        model = User

        fields = [

            "role",
            "custom_role",
            "access_level",

            "is_active",

        ]
