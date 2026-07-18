from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import User


class AccountsAPITests(APITestCase):

    password = "StrongPass123!"

    def setUp(self):
        self.user = User.objects.create_user(
            username="customer",
            email="customer@example.com",
            password=self.password,
            role=User.Role.USER,
        )

        self.trader = User.objects.create_user(
            username="trader",
            email="trader@example.com",
            password=self.password,
            role=User.Role.TRADER,
        )

        self.super_admin = User.objects.create_user(
            username="superadmin",
            email="superadmin@example.com",
            password=self.password,
            role=User.Role.SUPER_ADMIN,
            is_staff=True,
            is_superuser=True,
        )

    def authenticate(self, user):
        response = self.client.post(
            "/api/token/",
            {
                "username": user.username,
                "password": self.password,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.client.credentials(
            HTTP_AUTHORIZATION=(
                f"Bearer {response.data['access']}"
            )
        )

        return response

    def test_register_creates_regular_user(self):
        response = self.client.post(
            reverse("register"),
            {
                "username": "newcustomer",
                "email": "NEW@example.com",
                "password": self.password,
                "first_name": "New",
                "last_name": "Customer",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        created_user = User.objects.get(
            username="newcustomer"
        )

        self.assertEqual(
            created_user.role,
            User.Role.USER,
        )

        self.assertEqual(
            created_user.email,
            "new@example.com",
        )

        self.assertTrue(
            created_user.check_password(
                self.password
            )
        )

    def test_register_rejects_duplicate_email(self):
        response = self.client.post(
            reverse("register"),
            {
                "username": "anothercustomer",
                "email": "CUSTOMER@EXAMPLE.COM",
                "password": self.password,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertFalse(
            response.data["success"]
        )

        self.assertIn(
            "email",
            response.data["errors"],
        )

    def test_login_returns_tokens_and_role(self):
        response = self.authenticate(
            self.trader
        )

        self.assertIn(
            "access",
            response.data,
        )

        self.assertIn(
            "refresh",
            response.data,
        )

        self.assertEqual(
            response.data["user"]["id"],
            self.trader.id,
        )

        self.assertEqual(
            response.data["user"]["role"],
            User.Role.TRADER,
        )

    def test_refresh_returns_access_token(self):
        login_response = self.authenticate(
            self.user
        )

        self.client.credentials()

        response = self.client.post(
            "/api/token/refresh/",
            {
                "refresh": (
                    login_response.data["refresh"]
                )
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertIn(
            "access",
            response.data,
        )

    def test_profile_requires_authentication(self):
        response = self.client.get(
            reverse("profile")
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_user_can_read_and_update_profile(self):
        self.authenticate(self.user)

        response = self.client.get(
            reverse("profile")
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            response.data["username"],
            self.user.username,
        )

        response = self.client.patch(
            reverse("profile"),
            {
                "first_name": "Updated",
                "phone": "09120000000",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.user.refresh_from_db()

        self.assertEqual(
            self.user.first_name,
            "Updated",
        )

        self.assertEqual(
            self.user.phone,
            "09120000000",
        )

    def test_regular_user_cannot_list_users(self):
        self.authenticate(self.user)

        response = self.client.get(
            "/api/accounts/users/"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_super_admin_can_manage_role(self):
        self.authenticate(self.super_admin)

        response = self.client.get(
            "/api/accounts/users/"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        response = self.client.patch(
            reverse(
                "user-role-update",
                kwargs={"pk": self.user.pk},
            ),
            {
                "role": User.Role.TRADER,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.user.refresh_from_db()

        self.assertEqual(
            self.user.role,
            User.Role.TRADER,
        )

    def test_super_admin_can_toggle_user(self):
        self.authenticate(self.super_admin)

        response = self.client.post(
            (
                "/api/accounts/users/"
                f"{self.user.pk}/toggle/"
            ),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.user.refresh_from_db()

        self.assertFalse(
            self.user.is_active
        )

    def test_super_admin_cannot_modify_itself(self):
        self.authenticate(self.super_admin)

        role_response = self.client.patch(
            reverse(
                "user-role-update",
                kwargs={
                    "pk": self.super_admin.pk
                },
            ),
            {
                "role": User.Role.USER,
            },
            format="json",
        )

        status_response = self.client.post(
            (
                "/api/accounts/users/"
                f"{self.super_admin.pk}/toggle/"
            ),
            format="json",
        )

        self.assertEqual(
            role_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertEqual(
            status_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )