from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import PlatformRole, User

from .models import LandingPage, LandingSection


class LandingAPITests(APITestCase):
    password = "StrongPassword!123"

    def setUp(self):
        self.page, _ = LandingPage.objects.get_or_create(site_key="main")
        self.admin = User.objects.create_user(
            username="landing-admin",
            password=self.password,
            role=User.Role.ADMIN,
        )
        self.user = User.objects.create_user(
            username="landing-user",
            password=self.password,
        )
        self.public_url = reverse("landing-public")
        self.page_manage_url = reverse("landing-page-management")
        self.sections_url = reverse("landing-section-list-create")

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def test_public_landing_does_not_require_authentication(self):
        self.page.site_name = "Sokanex"
        self.page.save(update_fields=["site_name", "updated_at"])
        response = self.client.get(self.public_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["site_name"], "Sokanex")
        self.assertEqual(response.data["sections"], [])

    def test_public_landing_only_returns_active_ordered_sections(self):
        LandingSection.objects.create(
            page=self.page,
            key="second",
            title="Second",
            display_order=20,
        )
        LandingSection.objects.create(
            page=self.page,
            key="first",
            title="First",
            display_order=10,
        )
        LandingSection.objects.create(
            page=self.page,
            key="hidden",
            title="Hidden",
            display_order=0,
            is_active=False,
        )
        response = self.client.get(self.public_url)
        self.assertEqual(
            [item["key"] for item in response.data["sections"]],
            ["first", "second"],
        )

    def test_inactive_page_is_not_public(self):
        self.page.is_active = False
        self.page.save(update_fields=["is_active", "updated_at"])
        response = self.client.get(self.public_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_regular_user_cannot_manage_landing(self):
        self.authenticate(self.user)
        page_response = self.client.patch(
            self.page_manage_url,
            {"site_name": "Unauthorized"},
            format="json",
        )
        section_response = self.client.post(
            self.sections_url,
            {"key": "unauthorized"},
            format="json",
        )
        self.assertEqual(
            page_response.status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            section_response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_admin_can_update_page_and_manage_sections(self):
        self.authenticate(self.admin)
        page_response = self.client.patch(
            self.page_manage_url,
            {
                "site_name": "Sokanex",
                "meta_title": "Sokanex trading platform",
                "social_links": {
                    "instagram": "https://instagram.com/sokanex",
                },
            },
            format="json",
        )
        self.assertEqual(page_response.status_code, status.HTTP_200_OK)

        create_response = self.client.post(
            self.sections_url,
            {
                "key": "hero",
                "section_type": LandingSection.Type.HERO,
                "title": "Trade with confidence",
                "content": {"highlights": ["Signals", "Academy"]},
                "cta_label": "Get started",
                "cta_url": "/register",
                "display_order": 1,
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        section = LandingSection.objects.get(key="hero")
        self.assertEqual(section.created_by, self.admin)

        detail_url = reverse(
            "landing-section-detail",
            kwargs={"pk": section.pk},
        )
        patch_response = self.client.patch(
            detail_url,
            {"title": "Updated hero"},
            format="json",
        )
        self.assertEqual(patch_response.status_code, status.HTTP_200_OK)
        delete_response = self.client.delete(detail_url)
        self.assertEqual(
            delete_response.status_code,
            status.HTTP_204_NO_CONTENT,
        )

    def test_section_content_must_be_an_object(self):
        self.authenticate(self.admin)
        response = self.client.post(
            self.sections_url,
            {
                "key": "invalid-content",
                "content": ["not", "an", "object"],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("content", response.data["errors"])

    def test_duplicate_section_key_is_rejected(self):
        LandingSection.objects.create(page=self.page, key="hero")
        self.authenticate(self.admin)
        response = self.client.post(
            self.sections_url,
            {"key": "hero"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("key", response.data["errors"])

    def test_custom_role_can_manage_landing(self):
        role = PlatformRole.objects.create(
            name="Landing manager",
            slug="landing-manager",
            permissions=[User.Permission.LANDING_MANAGE],
            created_by=self.admin,
        )
        self.user.custom_role = role
        self.user.save(update_fields=["custom_role"])
        self.authenticate(self.user)
        response = self.client.patch(
            self.page_manage_url,
            {"site_name": "Managed through custom role"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
