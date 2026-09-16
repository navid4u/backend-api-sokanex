from django.core.management import call_command
from rest_framework.test import APITestCase

from apps.accounts.models import User

from .models import AssetCatalogItem, AssetCategory, UserAssetHolding


class AssetCatalogAndHoldingAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_asset_catalog", verbosity=0)
        cls.user = User.objects.create_user(username="asset-owner", password="pass")
        cls.other = User.objects.create_user(username="asset-other", password="pass")

    def setUp(self):
        self.client.force_authenticate(self.user)

    def test_catalog_contains_complete_reference_without_duplicates(self):
        response = self.client.get("/api/assets/catalog/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 18)
        self.assertEqual(
            sum(len(category["assets"]) for category in response.data["results"]),
            349,
        )
        self.assertEqual(AssetCategory.objects.values("code").distinct().count(), 18)
        self.assertEqual(AssetCatalogItem.objects.values("code").distinct().count(), 349)

    def test_seed_is_idempotent(self):
        call_command("seed_asset_catalog", verbosity=0)
        call_command("seed_asset_catalog", verbosity=0)
        self.assertEqual(AssetCategory.objects.count(), 18)
        self.assertEqual(AssetCatalogItem.objects.count(), 349)

    def test_create_and_upsert_holding(self):
        created = self.client.post(
            "/api/assets/holdings/",
            {"asset_code": "gold-001", "quantity": "12.50000000", "unit": "دستکاری"},
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["unit"], "گرم")
        updated = self.client.post(
            "/api/assets/holdings/",
            {"asset_code": "gold-001", "quantity": "7.25000000", "unit": "عدد"},
            format="json",
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data["id"], created.data["id"])
        self.assertEqual(updated.data["quantity"], "7.25000000")
        self.assertEqual(UserAssetHolding.objects.count(), 1)
        self.assertEqual(UserAssetHolding.objects.get().unit, "GRAM")

    def test_owner_isolation_and_foreign_detail_is_404(self):
        asset = AssetCatalogItem.objects.get(code="gold-001")
        own = UserAssetHolding.objects.create(
            user=self.user, asset=asset, quantity=1, unit=asset.unit
        )
        foreign = UserAssetHolding.objects.create(
            user=self.other, asset=asset, quantity=2, unit=asset.unit
        )
        listing = self.client.get("/api/assets/holdings/")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual([row["id"] for row in listing.data["results"]], [own.id])
        self.assertEqual(
            self.client.patch(
                f"/api/assets/holdings/{foreign.id}/", {"quantity": "3"}, format="json"
            ).status_code,
            404,
        )
        self.assertEqual(self.client.delete(f"/api/assets/holdings/{foreign.id}/").status_code, 404)

    def test_invalid_quantities_and_inactive_asset_are_rejected(self):
        for quantity in ("0", "-1", "invalid"):
            response = self.client.post(
                "/api/assets/holdings/",
                {"asset_code": "gold-001", "quantity": quantity},
                format="json",
            )
            self.assertEqual(response.status_code, 400)
        asset = AssetCatalogItem.objects.get(code="gold-001")
        asset.is_active = False
        asset.save(update_fields=["is_active"])
        response = self.client.post(
            "/api/assets/holdings/",
            {"asset_code": "gold-001", "quantity": "1"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_owner_can_patch_only_quantity_and_note_then_delete(self):
        asset = AssetCatalogItem.objects.get(code="coin-001")
        holding = UserAssetHolding.objects.create(
            user=self.user, asset=asset, quantity=1, unit=asset.unit
        )
        patched = self.client.patch(
            f"/api/assets/holdings/{holding.id}/",
            {"quantity": "2.00000000", "note": "دارایی شخصی"},
            format="json",
        )
        self.assertEqual(patched.status_code, 200)
        self.assertEqual(patched.data["unit"], "عدد")
        forbidden = self.client.patch(
            f"/api/assets/holdings/{holding.id}/",
            {"asset_code": "gold-001"},
            format="json",
        )
        self.assertEqual(forbidden.status_code, 400)
        self.assertEqual(self.client.delete(f"/api/assets/holdings/{holding.id}/").status_code, 204)

    def test_catalog_and_holdings_require_authentication(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get("/api/assets/catalog/").status_code, 401)
        self.assertEqual(self.client.get("/api/assets/holdings/").status_code, 401)

