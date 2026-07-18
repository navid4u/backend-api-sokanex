import django_filters

from .models import Article


class ArticleFilter(django_filters.FilterSet):

    category = django_filters.CharFilter(
        field_name="category__slug",
    )

    class Meta:
        model = Article

        fields = (
            "category",
            "status",
            "author",
        )