import django_filters

from .models import Video


class VideoFilter(django_filters.FilterSet):

    category = django_filters.CharFilter(
        field_name="category__slug",
    )

    class Meta:
        model = Video

        fields = (
            "category",
            "status",
            "author",
        )