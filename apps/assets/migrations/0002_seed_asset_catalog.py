from django.db import migrations


def seed_catalog(apps, schema_editor):
    from apps.assets.catalog import seed_asset_catalog

    category_model = apps.get_model("assets", "AssetCategory")
    item_model = apps.get_model("assets", "AssetCatalogItem")
    seed_asset_catalog(category_model, item_model)


class Migration(migrations.Migration):
    dependencies = [("assets", "0001_initial")]
    operations = [migrations.RunPython(seed_catalog, migrations.RunPython.noop)]

