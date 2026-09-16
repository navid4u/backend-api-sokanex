from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.assets.catalog import seed_asset_catalog
from apps.assets.models import AssetCatalogItem, AssetCategory
from apps.assets.signals import CATALOG_CACHE_KEY


class Command(BaseCommand):
    help = "Idempotently seed or update the Persian asset catalog."

    def handle(self, *args, **options):
        with transaction.atomic():
            categories, items = seed_asset_catalog(AssetCategory, AssetCatalogItem)
        cache.delete(CATALOG_CACHE_KEY)
        self.stdout.write(self.style.SUCCESS(
            f"Asset catalog seeded: categories={categories} items={items}"
        ))

