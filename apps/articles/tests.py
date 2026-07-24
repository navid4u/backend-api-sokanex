import base64
import tempfile
from datetime import timedelta

from django.core.files.uploadedfile import (
    SimpleUploadedFile,
)
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.articles.models import (
    Article,
    Category,
)

class ArticleAPITests(APITestCase):
    def cover_image(self, name="cover.png"):
        image_content = base64.b64decode(
            (
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB"
                "CAQAAAC1HAwCAAAAC0lEQVR42mNk"
                "YAAAAAYAAjCB0C8AAAAASUVORK5CYII="
            )
        )

        return SimpleUploadedFile(
            name=name,
            content=image_content,
            content_type="image/png",
        )
    def test_employee_can_create_article_with_cover(
        self
    ):
        self.authenticate(self.employee)

        response = self.client.post(
            reverse("article-list-create"),
            {
                "title": "Article with image",
                "summary": "Article summary",
                "content": "Article content",
                "category": self.category.pk,
                "status": Article.Status.DRAFT,
                "cover_image": self.cover_image(),
            },
            format="multipart",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            response.data,
        )

        article = Article.objects.get(
            pk=response.data["id"]
        )

        self.assertTrue(
            article.cover_image.name.startswith(
                "articles/"
            )
        )

        self.assertEqual(
            article.category,
            self.category,
        )
        

    def test_article_rejects_invalid_cover_image(
        self
    ):
        self.authenticate(self.employee)

        invalid_image = SimpleUploadedFile(
            name="cover.txt",
            content=b"not a valid image",
            content_type="text/plain",
        )

        response = self.client.post(
            reverse("article-list-create"),
            {
                "title": "Invalid cover",
                "summary": "Article summary",
                "content": "Article content",
                "category": self.category.pk,
                "status": Article.Status.DRAFT,
                "cover_image": invalid_image,
            },
            format="multipart",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertIn(
            "cover_image",
            response.data["errors"],
        )
        
    def test_article_list_returns_cover_and_category(
        self
    ):
        self.published_article.cover_image = (
            self.cover_image(
                name="published-cover.png"
            )
        )

        self.published_article.save(
            update_fields=[
                "cover_image",
            ]
        )

        self.authenticate(self.user)

        response = self.client.get(
            reverse("article-list-create")
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        returned_article = next(
            item
            for item in response.data["results"]
            if (
                item["id"]
                == self.published_article.id
            )
        )

        self.assertIsNotNone(
            returned_article["cover_image"]
        )

        self.assertEqual(
            returned_article["category"]["id"],
            self.category.id,
        )

        self.assertEqual(
            returned_article["category"]["name"],
            self.category.name,
        )

        self.assertEqual(
            returned_article["category"]["slug"],
            self.category.slug,
        )

    def test_category_must_be_sent_as_category(
        self
    ):
        self.authenticate(self.employee)

        response = self.client.post(
            reverse("article-list-create"),
            {
                "title": "Correct category field",
                "summary": "Article summary",
                "content": "Article content",
                "category": self.category.pk,
                "status": Article.Status.DRAFT,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            response.data,
        )

        article = Article.objects.get(
            pk=response.data["id"]
        )

        self.assertEqual(
            article.category,
            self.category,
        )

    def setUp(self):
        self.media_directory = (
            tempfile.TemporaryDirectory()
        )

        self.media_override = override_settings(
            MEDIA_ROOT=self.media_directory.name
        )

        self.media_override.enable()

        self.addCleanup(
            self.media_override.disable
        )

        self.addCleanup(
            self.media_directory.cleanup
        )
        password = "StrongPass123!"

        self.user = User.objects.create_user(
            username="customer",
            password=password,
            role=User.Role.USER,
        )

        self.trader = User.objects.create_user(
            username="trader",
            password=password,
            role=User.Role.TRADER,
        )

        self.employee = User.objects.create_user(
            username="employee",
            password=password,
            role=User.Role.EMPLOYEE,
        )

        self.category = Category.objects.create(
            name="Trading basics"
        )

        self.published_article = Article.objects.create(
            title="Published article",
            summary="Published summary",
            content="Published content",
            category=self.category,
            author=self.employee,
            status=Article.Status.PUBLISHED,
            published_at=timezone.now(),
        )

        self.draft_article = Article.objects.create(
            title="Draft article",
            summary="Draft summary",
            content="Draft content",
            category=self.category,
            author=self.employee,
            status=Article.Status.DRAFT,
        )

        self.future_article = Article.objects.create(
            title="Future article",
            summary="Future summary",
            content="Future content",
            category=self.category,
            author=self.employee,
            status=Article.Status.PUBLISHED,
            published_at=(
                timezone.now()
                + timedelta(days=1)
            ),
        )

    def test_user_cannot_update_category(self):
        self.authenticate(self.user)

        response = self.client.patch(
            reverse(
                "category-detail",
                kwargs={
                    "pk": self.category.pk,
                },
            ),
            {
                "name": "Updated category",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.category.refresh_from_db()

        self.assertEqual(
            self.category.name,
            "Trading basics",
        )

    def test_employee_can_update_category(self):
        self.authenticate(self.employee)

        response = self.client.patch(
            reverse(
                "category-detail",
                kwargs={
                    "pk": self.category.pk,
                },
            ),
            {
                "name": "Updated category",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.category.refresh_from_db()

        self.assertEqual(
            self.category.name,
            "Updated category",
        )

    def test_user_cannot_delete_category(self):
        self.authenticate(self.user)

        response = self.client.delete(
            reverse(
                "category-detail",
                kwargs={
                    "pk": self.category.pk,
                },
            )
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.assertTrue(
            Category.objects.filter(
                pk=self.category.pk
            ).exists()
        )

    def test_employee_can_delete_category(self):
        self.authenticate(self.employee)

        response = self.client.delete(
            reverse(
                "category-detail",
                kwargs={
                    "pk": self.category.pk,
                },
            )
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_204_NO_CONTENT,
        )

        self.assertFalse(
            Category.objects.filter(
                pk=self.category.pk
            ).exists()
        )

        self.published_article.refresh_from_db()

        self.assertIsNone(
            self.published_article.category
        )
    def authenticate(self, user):
        self.client.force_authenticate(
            user=user
        )

    def article_payload(
        self,
        status_value=Article.Status.DRAFT,
    ):
        return {
            "title": "New article",
            "summary": "New summary",
            "content": "New article content",
            "category": self.category.pk,
            "status": status_value,
        }

    def test_list_requires_authentication(self):
        response = self.client.get(
            reverse("article-list-create")
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_user_only_sees_published_articles(
        self
    ):
        self.authenticate(self.user)

        response = self.client.get(
            reverse("article-list-create")
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        returned_ids = {
            item["id"]
            for item in response.data["results"]
        }

        self.assertIn(
            self.published_article.id,
            returned_ids,
        )

        self.assertNotIn(
            self.draft_article.id,
            returned_ids,
        )

        self.assertNotIn(
            self.future_article.id,
            returned_ids,
        )

    def test_user_cannot_open_draft(self):
        self.authenticate(self.user)

        response = self.client.get(
            reverse(
                "article-detail",
                kwargs={
                    "slug": self.draft_article.slug
                },
            )
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_user_and_trader_cannot_create(
        self
    ):
        for actor in (
            self.user,
            self.trader,
        ):
            self.authenticate(actor)

            response = self.client.post(
                reverse("article-list-create"),
                self.article_payload(),
                format="json",
            )

            self.assertEqual(
                response.status_code,
                status.HTTP_403_FORBIDDEN,
            )

    def test_user_cannot_create_category(self):
        self.authenticate(self.user)

        response = self.client.post(
            reverse("category-list-create"),
            {
                "name": "Technical analysis",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_employee_can_create_category(self):
        self.authenticate(self.employee)

        response = self.client.post(
            reverse("category-list-create"),
            {
                "name": "Technical analysis",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertTrue(
            Category.objects.filter(
                name="Technical analysis"
            ).exists()
        )

    def test_employee_can_create_draft(self):
        self.authenticate(self.employee)

        response = self.client.post(
            reverse("article-list-create"),
            self.article_payload(),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        article = Article.objects.get(
            pk=response.data["id"]
        )

        self.assertEqual(
            article.author,
            self.employee,
        )

        self.assertEqual(
            article.status,
            Article.Status.DRAFT,
        )

        self.assertIsNone(
            article.published_at
        )

    def test_employee_can_publish_article(self):
        self.authenticate(self.employee)

        response = self.client.post(
            reverse("article-list-create"),
            self.article_payload(
                Article.Status.PUBLISHED
            ),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        article = Article.objects.get(
            pk=response.data["id"]
        )

        self.assertEqual(
            article.status,
            Article.Status.PUBLISHED,
        )

        self.assertIsNotNone(
            article.published_at
        )

    def test_management_list_includes_drafts(
        self
    ):
        self.authenticate(self.employee)

        response = self.client.get(
            reverse("article-management-list")
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        returned_ids = {
            item["id"]
            for item in response.data["results"]
        }

        self.assertIn(
            self.published_article.id,
            returned_ids,
        )

        self.assertIn(
            self.draft_article.id,
            returned_ids,
        )

    def test_employee_can_publish_existing_draft(
        self
    ):
        self.authenticate(self.employee)

        response = self.client.patch(
            reverse(
                "article-detail",
                kwargs={
                    "slug": self.draft_article.slug
                },
            ),
            {
                "status": Article.Status.PUBLISHED,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.draft_article.refresh_from_db()

        self.assertEqual(
            self.draft_article.status,
            Article.Status.PUBLISHED,
        )

        self.assertIsNotNone(
            self.draft_article.published_at
        )

    def test_employee_can_return_to_draft(
        self
    ):
        self.authenticate(self.employee)

        response = self.client.patch(
            reverse(
                "article-detail",
                kwargs={
                    "slug": (
                        self.published_article.slug
                    )
                },
            ),
            {
                "status": Article.Status.DRAFT,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.published_article.refresh_from_db()

        self.assertEqual(
            self.published_article.status,
            Article.Status.DRAFT,
        )

        self.assertIsNone(
            self.published_article.published_at
        )

    def test_delete_permissions(self):
        detail_url = reverse(
            "article-detail",
            kwargs={
                "slug": (
                    self.published_article.slug
                )
            },
        )

        self.authenticate(self.user)

        response = self.client.delete(
            detail_url
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.authenticate(self.employee)

        response = self.client.delete(
            detail_url
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_204_NO_CONTENT,
        )

        self.assertFalse(
            Article.objects.filter(
                pk=self.published_article.pk
            ).exists()
        )
        
    def test_authenticated_user_can_list_categories(
        self
    ):
        self.authenticate(self.user)

        response = self.client.get(
            reverse("category-list-create")
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        returned_ids = {
            item["id"]
            for item in response.data["results"]
        }

        self.assertIn(
            self.category.id,
            returned_ids,
        )


    def test_authenticated_user_can_retrieve_category(
        self
    ):
        self.authenticate(self.user)

        response = self.client.get(
            reverse(
                "category-detail",
                kwargs={
                    "pk": self.category.pk,
                },
            )
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            response.data["id"],
            self.category.pk,
        )

        self.assertEqual(
            response.data["name"],
            self.category.name,
        )

        self.assertEqual(
            response.data["slug"],
            self.category.slug,
        )


    def test_employee_can_change_article_category(
        self
    ):
        second_category = Category.objects.create(
            name="Risk management"
        )

        self.authenticate(self.employee)

        response = self.client.patch(
            reverse(
                "article-detail",
                kwargs={
                    "slug": self.draft_article.slug,
                },
            ),
            {
                "category": second_category.pk,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
            response.data,
        )

        self.draft_article.refresh_from_db()

        self.assertEqual(
            self.draft_article.category,
            second_category,
        )


    def test_category_id_is_not_accepted(
        self
    ):
        second_category = Category.objects.create(
            name="Market analysis"
        )

        self.authenticate(self.employee)

        response = self.client.patch(
            reverse(
                "article-detail",
                kwargs={
                    "slug": self.draft_article.slug,
                },
            ),
            {
                "category_id": second_category.pk,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.draft_article.refresh_from_db()

        self.assertEqual(
            self.draft_article.category,
            self.category,
        )


    def test_user_cannot_update_article(
        self
    ):
        self.authenticate(self.user)

        response = self.client.patch(
            reverse(
                "article-detail",
                kwargs={
                    "slug": self.published_article.slug,
                },
            ),
            {
                "title": "Unauthorized title",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.published_article.refresh_from_db()

        self.assertEqual(
            self.published_article.title,
            "Published article",
        )
