from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import UpgradeRequest, User
from apps.articles.models import Article
from apps.signals.models import (
    Direction,
    MarketType,
    Signal,
    SignalStatus,
)


class AccessLevelAPITests(APITestCase):
    password = "StrongPassword!123"

    def setUp(self):
        self.user = User.objects.create_user(
            username="level-user",
            password=self.password,
            access_level=1,
        )
        self.admin = User.objects.create_user(
            username="admin-user",
            password=self.password,
            role=User.Role.ADMIN,
        )

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def test_new_user_defaults_to_level_one(self):
        user = User.objects.create_user(
            username="new-level-user",
            password=self.password,
        )
        self.assertEqual(user.access_level, 1)

    def test_profile_exposes_access_level(self):
        self.authenticate(self.user)
        response = self.client.get(reverse("profile"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["access_level"], 1)

    def test_user_only_sees_articles_for_own_level(self):
        Article.objects.create(
            title="Level one",
            content="Visible",
            status=Article.Status.PUBLISHED,
            published_at="2026-01-01T00:00:00Z",
            allowed_level_1=True,
            allowed_level_2=False,
            allowed_level_3=False,
            allowed_level_4=False,
            allowed_level_5=False,
        )
        Article.objects.create(
            title="Level two",
            content="Hidden",
            status=Article.Status.PUBLISHED,
            published_at="2026-01-01T00:00:00Z",
            allowed_level_1=False,
            allowed_level_2=True,
            allowed_level_3=False,
            allowed_level_4=False,
            allowed_level_5=False,
        )
        self.authenticate(self.user)
        response = self.client.get("/api/articles/")
        titles = [item["title"] for item in response.data["results"]]
        self.assertEqual(titles, ["Level one"])

    def test_admin_sees_all_levels(self):
        Signal.objects.create(
            title="Level five signal",
            symbol="BTCUSDT",
            market=MarketType.CRYPTO,
            direction=Direction.BUY,
            entry_price=100,
            stop_loss=90,
            take_profit=110,
            status=SignalStatus.APPROVED,
            created_by=self.admin,
            allowed_level_1=False,
            allowed_level_5=True,
        )
        self.authenticate(self.admin)
        response = self.client.get("/api/signals/")
        self.assertEqual(response.data["count"], 1)

    def test_only_one_pending_request_is_allowed(self):
        self.authenticate(self.user)
        response = self.client.post(
            reverse("my-upgrade-requests"),
            {
                "request_type": UpgradeRequest.Type.UPGRADE,
                "requested_level": 3,
                "message": "Please upgrade me.",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        duplicate = self.client.post(
            reverse("my-upgrade-requests"),
            {
                "request_type": UpgradeRequest.Type.PREMIUM,
                "requested_level": 5,
            },
            format="json",
        )
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)

    def test_premium_request_requires_level_five(self):
        self.authenticate(self.user)
        response = self.client.post(
            reverse("my-upgrade-requests"),
            {
                "request_type": UpgradeRequest.Type.PREMIUM,
                "requested_level": 4,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_admin_approval_updates_user_level(self):
        upgrade_request = UpgradeRequest.objects.create(
            user=self.user,
            requested_level=4,
        )
        self.authenticate(self.admin)
        response = self.client.patch(
            reverse(
                "upgrade-request-review",
                kwargs={"pk": upgrade_request.pk},
            ),
            {"status": UpgradeRequest.Status.APPROVED},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        upgrade_request.refresh_from_db()
        self.assertEqual(self.user.access_level, 4)
        self.assertEqual(
            upgrade_request.status,
            UpgradeRequest.Status.APPROVED,
        )

    def test_employee_cannot_manage_upgrade_requests(self):
        employee = User.objects.create_user(
            username="employee",
            password=self.password,
            role=User.Role.EMPLOYEE,
        )
        self.authenticate(employee)
        response = self.client.get(
            reverse("upgrade-request-management")
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
