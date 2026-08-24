from rest_framework.test import APITestCase

from apps.wallet.models import UpgradePlan
from apps.wallet.services import WalletService
from .models import PlatformRole, UpgradeRequest, User


class RoleAndUpgradeV2Tests(APITestCase):
    def setUp(self):
        self.support = User.objects.get(username="support")
        self.super_admin = User.objects.create_user(username="super-v2", password="pass", role=User.Role.SUPER_ADMIN)
        self.user = User.objects.create_user(username="upgrade-v2", password="pass", access_level=1)

    def test_support_has_only_support_management(self):
        self.assertTrue(self.support.has_platform_permission(User.Permission.SUPPORT_MANAGE))
        for permission in (
            User.Permission.USER_MANAGE, User.Permission.CONTENT_MANAGE,
            User.Permission.SIGNAL_REVIEW, User.Permission.ROLE_MANAGE,
            User.Permission.PLATFORM_SETTINGS_MANAGE,
        ):
            self.assertFalse(self.support.has_platform_permission(permission))

        custom_role = PlatformRole.objects.create(
            name="Unsafe support grants",
            permissions=[User.Permission.USER_MANAGE, User.Permission.CONTENT_MANAGE],
        )
        self.support.custom_role = custom_role
        self.support.save(update_fields=["custom_role", "updated_at"])
        self.assertFalse(self.support.has_platform_permission(User.Permission.USER_MANAGE))
        self.assertFalse(self.support.has_platform_permission(User.Permission.CONTENT_MANAGE))

    def test_dashboard_exposes_platform_capability(self):
        self.client.force_authenticate(self.super_admin)
        response = self.client.get("/api/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["data"]["capabilities"]["can_manage_platform"])

    def test_upgrade_hold_and_reject_release(self):
        plan = UpgradePlan.objects.get(level=2)
        plan.price_irt = 200000
        plan.save(update_fields=["price_irt"])
        wallet = WalletService.get_wallet(self.user)
        WalletService.post(wallet, 300000, "TEST_CREDIT")
        self.client.force_authenticate(self.user)
        created = self.client.post("/api/accounts/upgrade-requests/", {"requested_level": 2, "request_type": "UPGRADE"}, format="json")
        self.assertEqual(created.status_code, 201)
        self.assertEqual(WalletService.balance_irt(wallet), 100000)
        self.client.force_authenticate(self.super_admin)
        reviewed = self.client.patch(f"/api/accounts/admin/upgrade-requests/{created.data['id']}/review/", {"status": "REJECTED"}, format="json")
        self.assertEqual(reviewed.status_code, 200)
        self.assertEqual(WalletService.balance_irt(wallet), 300000)

    def test_upgrade_approve_captures_and_changes_level(self):
        plan = UpgradePlan.objects.get(level=3)
        plan.price_irt = 150000
        plan.save(update_fields=["price_irt"])
        wallet = WalletService.get_wallet(self.user)
        WalletService.post(wallet, 200000, "TEST_CREDIT")
        self.client.force_authenticate(self.user)
        created = self.client.post("/api/accounts/upgrade-requests/", {"requested_level": 3, "request_type": "UPGRADE"}, format="json")
        self.client.force_authenticate(self.super_admin)
        self.assertEqual(self.client.patch(f"/api/accounts/admin/upgrade-requests/{created.data['id']}/review/", {"status": "APPROVED"}, format="json").status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.access_level, 3)
        self.assertEqual(WalletService.balance_irt(wallet), 50000)
