from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.academy.models import Course

from .models import User, UserProfile


class AdminUserCrudAPITests(APITestCase):
    password = "StrongPassword!123"

    def setUp(self):
        self.admin = User.objects.create_user(
            username="user-manager",
            password=self.password,
            role=User.Role.ADMIN,
        )
        self.super_admin = User.objects.create_user(
            username="super-user-manager",
            password=self.password,
            role=User.Role.SUPER_ADMIN,
        )
        self.user = User.objects.create_user(
            username="managed-user",
            email="managed@example.com",
            password=self.password,
        )
        self.other_admin = User.objects.create_user(
            username="other-admin",
            password=self.password,
            role=User.Role.ADMIN,
        )

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def test_admin_can_create_user_with_hashed_password_and_profile(self):
        self.authenticate(self.admin)
        response = self.client.post(
            reverse("user-list"),
            {
                "username": "created-by-admin",
                "email": "Created@Example.com",
                "password": self.password,
                "first_name": "Created",
                "role": User.Role.TRADER,
                "access_level": 3,
                "is_active": True,
                "is_verified": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = User.objects.get(username="created-by-admin")
        self.assertTrue(created.check_password(self.password))
        self.assertEqual(created.email, "created@example.com")
        self.assertEqual(created.role, User.Role.TRADER)
        self.assertEqual(created.access_level, 3)
        self.assertTrue(
            UserProfile.objects.filter(user=created).exists()
        )
        self.assertNotIn("password", response.data)

    def test_password_is_required_when_creating_user(self):
        self.authenticate(self.admin)
        response = self.client.post(
            reverse("user-list"),
            {
                "username": "missing-password",
                "email": "missing@example.com",
            },
            format="json",
        )
        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn("password", response.data["errors"])

    def test_admin_can_retrieve_patch_put_and_delete_regular_user(self):
        self.authenticate(self.admin)
        detail_url = reverse(
            "user-detail",
            kwargs={"pk": self.user.pk},
        )

        retrieve = self.client.get(detail_url)
        self.assertEqual(retrieve.status_code, status.HTTP_200_OK)
        self.assertEqual(retrieve.data["id"], self.user.pk)

        patch = self.client.patch(
            detail_url,
            {
                "first_name": "Patched",
                "access_level": 4,
            },
            format="json",
        )
        self.assertEqual(patch.status_code, status.HTTP_200_OK)

        put = self.client.put(
            detail_url,
            {
                "username": self.user.username,
                "email": self.user.email,
                "first_name": "Replaced",
                "last_name": "User",
                "role": User.Role.USER,
                "access_level": 2,
                "is_active": True,
                "is_verified": False,
            },
            format="json",
        )
        self.assertEqual(put.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Replaced")
        self.assertEqual(self.user.access_level, 2)
        self.assertTrue(self.user.check_password(self.password))

        delete = self.client.delete(detail_url)
        self.assertEqual(
            delete.status_code,
            status.HTTP_204_NO_CONTENT,
        )
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())

    def test_regular_user_cannot_use_admin_user_endpoints(self):
        self.authenticate(self.user)
        list_response = self.client.get(reverse("user-list"))
        detail_response = self.client.get(
            reverse(
                "user-detail",
                kwargs={"pk": self.other_admin.pk},
            )
        )
        self.assertEqual(
            list_response.status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            detail_response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_admin_cannot_create_or_modify_administrator(self):
        self.authenticate(self.admin)
        create_response = self.client.post(
            reverse("user-list"),
            {
                "username": "unauthorized-admin",
                "password": self.password,
                "role": User.Role.ADMIN,
            },
            format="json",
        )
        update_response = self.client.patch(
            reverse(
                "user-detail",
                kwargs={"pk": self.other_admin.pk},
            ),
            {"first_name": "Unauthorized"},
            format="json",
        )
        delete_response = self.client.delete(
            reverse(
                "user-detail",
                kwargs={"pk": self.other_admin.pk},
            )
        )
        self.assertEqual(
            create_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            update_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            delete_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_super_admin_can_manage_administrator(self):
        self.authenticate(self.super_admin)
        detail_url = reverse(
            "user-detail",
            kwargs={"pk": self.other_admin.pk},
        )
        update_response = self.client.patch(
            detail_url,
            {"first_name": "Updated by super admin"},
            format="json",
        )
        self.assertEqual(
            update_response.status_code,
            status.HTTP_200_OK,
        )
        delete_response = self.client.delete(detail_url)
        self.assertEqual(
            delete_response.status_code,
            status.HTTP_204_NO_CONTENT,
        )

    def test_manager_cannot_change_own_sensitive_fields_or_delete_self(self):
        self.authenticate(self.admin)
        detail_url = reverse(
            "user-detail",
            kwargs={"pk": self.admin.pk},
        )
        update_response = self.client.patch(
            detail_url,
            {
                "role": User.Role.USER,
                "is_active": False,
            },
            format="json",
        )
        delete_response = self.client.delete(detail_url)
        self.assertEqual(
            update_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            delete_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_duplicate_email_is_rejected_case_insensitively(self):
        self.authenticate(self.admin)
        response = self.client.post(
            reverse("user-list"),
            {
                "username": "duplicate-email",
                "email": "MANAGED@EXAMPLE.COM",
                "password": self.password,
            },
            format="json",
        )
        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn("email", response.data["errors"])

    def test_user_with_owned_course_cannot_be_deleted(self):
        Course.objects.create(
            title="Protected teacher course",
            instructor=self.user,
        )
        self.authenticate(self.admin)
        response = self.client.delete(
            reverse(
                "user-detail",
                kwargs={"pk": self.user.pk},
            )
        )
        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn("user", response.data["errors"])
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
