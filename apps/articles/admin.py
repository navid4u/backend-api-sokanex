from django.contrib import admin
from django.utils import timezone

from .models import Article, Category


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "name",
        "slug",
        "created_at",
    )

    search_fields = (
        "name",
        "slug",
    )

    ordering = (
        "name",
    )

    readonly_fields = (
        "created_at",
    )


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "title",
        "category",
        "author",
        "status",
        "published_at",
        "created_at",
    )

    list_filter = (
        "status",
        "category",
        "published_at",
        "created_at",
    )

    search_fields = (
        "title",
        "slug",
        "summary",
        "content",
        "author__username",
        "author__email",
    )

    ordering = (
        "-published_at",
        "-created_at",
    )

    list_select_related = (
        "category",
        "author",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    date_hierarchy = "published_at"

    actions = (
        "publish_articles",
        "move_to_draft",
    )

    fieldsets = (
        (
            "Article information",
            {
                "fields": (
                    "title",
                    "slug",
                    "summary",
                    "content",
                    "cover_image",
                    "category",
                ),
            },
        ),
        (
            "Publishing",
            {
                "fields": (
                    "author",
                    "status",
                    "published_at",
                ),
            },
        ),
        (
            "System information",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
                "classes": (
                    "collapse",
                ),
            },
        ),
    )

    def save_model(
        self,
        request,
        obj,
        form,
        change,
    ):
        if not obj.author_id:
            obj.author = request.user

        if (
            obj.status == Article.Status.PUBLISHED
            and obj.published_at is None
        ):
            obj.published_at = timezone.now()

        if obj.status == Article.Status.DRAFT:
            obj.published_at = None

        super().save_model(
            request,
            obj,
            form,
            change,
        )

    @admin.action(
        description="Publish selected articles",
    )
    def publish_articles(
        self,
        request,
        queryset,
    ):
        updated = queryset.update(
            status=Article.Status.PUBLISHED,
            published_at=timezone.now(),
        )

        self.message_user(
            request,
            f"{updated} article(s) published.",
        )

    @admin.action(
        description="Move selected articles to draft",
    )
    def move_to_draft(
        self,
        request,
        queryset,
    ):
        updated = queryset.update(
            status=Article.Status.DRAFT,
            published_at=None,
        )

        self.message_user(
            request,
            f"{updated} article(s) moved to draft.",
        )