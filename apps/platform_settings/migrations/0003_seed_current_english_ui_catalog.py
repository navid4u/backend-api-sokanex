"""Seed complete English UI labels from the current frontend dictionary.

Existing administrator translations win. The seed is intentionally a snapshot,
so deployment never needs filesystem access to the separate frontend checkout.
"""

import json
from pathlib import Path

from django.db import migrations


def seed_current_english_ui_catalog(apps, schema_editor):
    Catalog = apps.get_model("platform_settings", "UITranslationCatalog")
    database = schema_editor.connection.alias
    source = Path(__file__).resolve().parent.parent / "data" / "ui_en_20261010.json"
    defaults = json.loads(source.read_text(encoding="utf-8"))
    catalog, _ = Catalog.objects.using(database).get_or_create(locale="en")
    existing = catalog.translations or {}
    additions = {key: value for key, value in defaults.items() if key not in existing}
    if additions:
        catalog.translations = {**defaults, **existing}
        if existing:
            catalog.version += 1
        catalog.save(using=database, update_fields=("translations", "version", "updated_at"))


class Migration(migrations.Migration):
    dependencies = [("platform_settings", "0002_uitranslationcatalog_uitranslationauditlog")]

    operations = [migrations.RunPython(seed_current_english_ui_catalog, migrations.RunPython.noop)]
