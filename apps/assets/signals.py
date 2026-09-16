from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import AssetCatalogItem, AssetCategory


CATALOG_CACHE_KEY = "assets:catalog:v1"


@receiver([post_save, post_delete], sender=AssetCategory)
@receiver([post_save, post_delete], sender=AssetCatalogItem)
def invalidate_asset_catalog_cache(**kwargs):
    cache.delete(CATALOG_CACHE_KEY)

