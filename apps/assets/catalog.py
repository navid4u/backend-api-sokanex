import json
from pathlib import Path


CATALOG_PATH = Path(__file__).resolve().with_name("catalog_seed.json")


def load_catalog_seed():
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def seed_asset_catalog(category_model, item_model):
    category_count = 0
    item_count = 0
    for category_order, category_data in enumerate(load_catalog_seed(), start=1):
        category, _ = category_model.objects.update_or_create(
            code=category_data["code"],
            defaults={
                "title_fa": category_data["title"],
                "sort_order": category_order,
                "is_active": True,
            },
        )
        category_count += 1
        for item_order, item_data in enumerate(category_data["items"], start=1):
            item_model.objects.update_or_create(
                code=item_data["code"],
                defaults={
                    "category": category,
                    "name_fa": item_data["name"],
                    "risk_level": item_data["risk"],
                    "unit": item_data["unit"],
                    "sort_order": item_order,
                    "is_active": True,
                },
            )
            item_count += 1
    return category_count, item_count

