from datetime import timedelta

from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .models import User, UserProfile


class UserProfileDetailsAPITests(APITestCase):
    password = "StrongPassword!123"

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="profile-user",
            password=self.password,
        )
        self.other_user = User.objects.create_user(
            username="other-profile-user",
            password=self.password,
        )
        self.admin = User.objects.create_user(
            username="profile-admin",
            password=self.password,
            role=User.Role.ADMIN,
        )
        self.employee = User.objects.create_user(
            username="profile-employee",
            password=self.password,
            role=User.Role.EMPLOYEE,
        )

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def test_registration_creates_empty_profile_details(self):
        response = self.client.post(
            reverse("register"),
            {
                "username": "new-profile-user",
                "email": "new-profile@example.com",
                "password": self.password,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(username="new-profile-user")
        self.assertEqual(user.access_level, 1)
        self.assertTrue(
            UserProfile.objects.filter(user=user).exists()
        )

    def test_existing_user_profile_is_created_lazily(self):
        self.assertFalse(
            UserProfile.objects.filter(user=self.user).exists()
        )
        self.authenticate(self.user)
        response = self.client.get(reverse("profile-details"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            UserProfile.objects.filter(user=self.user).exists()
        )
        self.assertEqual(response.data["profile_completion"], 0)

    def test_user_can_update_structured_profile(self):
        self.authenticate(self.user)
        response = self.client.patch(
            reverse("profile-details"),
            {
                "birth_date": "1995-06-15",
                "country": "Iran",
                "city": "Tehran",
                "education_level": "BACHELOR",
                "occupation": "Engineer",
                "monthly_income_range": "1000_3000",
                "income_currency": "USD",
                "income_sources": ["SALARY", "TRADING"],
                "trading_experience_years": "2.5",
                "risk_tolerance": "MEDIUM",
                "investment_goal": "Long-term growth",
                "preferred_markets": ["CRYPTO", "FOREX"],
                "trading_frequency": "WEEKLY",
                "daily_free_time_minutes": 120,
                "learning_hours_weekly": "5.0",
                "preferred_learning_time": "EVENING",
                "exercise_days_per_week": 3,
                "sleep_hours_average": "7.5",
                "interests": ["finance", "technology"],
                "habits": {
                    "reads_market_news_daily": True,
                },
                "onboarding_answers": {
                    "primary_goal": "education",
                },
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(response.data["profile_completion"], 50)
        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(profile.city, "Tehran")
        self.assertEqual(profile.preferred_markets, ["CRYPTO", "FOREX"])

    def test_profile_rejects_invalid_values(self):
        self.authenticate(self.user)
        future_date = timezone.localdate() + timedelta(days=1)
        response = self.client.patch(
            reverse("profile-details"),
            {
                "birth_date": future_date.isoformat(),
                "preferred_markets": ["UNKNOWN"],
                "exercise_days_per_week": 8,
                "sleep_hours_average": "25.0",
            },
            format="json",
        )
        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn("birth_date", response.data["errors"])
        self.assertIn("preferred_markets", response.data["errors"])
        self.assertIn("exercise_days_per_week", response.data["errors"])

    def test_regular_user_cannot_read_another_profile(self):
        self.authenticate(self.user)
        response = self.client.get(
            reverse(
                "admin-user-profile-details",
                kwargs={"pk": self.other_user.pk},
            )
        )
        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_admin_can_read_user_profile(self):
        UserProfile.objects.create(
            user=self.user,
            occupation="Analyst",
            monthly_income_range=(
                UserProfile.IncomeRange.FROM_1000_TO_3000
            ),
        )
        self.authenticate(self.admin)
        response = self.client.get(
            reverse(
                "admin-user-profile-details",
                kwargs={"pk": self.user.pk},
            )
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["occupation"], "Analyst")

    def test_employee_cannot_read_private_profile(self):
        self.authenticate(self.employee)
        response = self.client.get(
            reverse(
                "admin-user-profile-details",
                kwargs={"pk": self.user.pk},
            )
        )
        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )
