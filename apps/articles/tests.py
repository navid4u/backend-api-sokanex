from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.articles.models import Article, Category


class ArticleAPITests(APITestCase):

    def setUp(self):
 
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