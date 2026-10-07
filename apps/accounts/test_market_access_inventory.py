import json
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings

from apps.accounts.models import User, UserMarketGrant


class MarketAccessInventoryTests(TestCase):
    @override_settings(MARKET_ACCESS_V2_ENABLED=False)
    def test_inventory_is_read_only_and_contains_no_user_identifiers(self):
        user = User.objects.create_user(
            username="snapshot-private-user",
            phone="09120000000",
            password="snapshot-private-password",
            access_level=User.AccessLevel.LEVEL_3,
        )
        UserMarketGrant.objects.create(
            user=user,
            market=User.MarketType.CRYPTO,
            source=UserMarketGrant.Source.ADMIN,
            granted_by=None,
        )
        before = UserMarketGrant.objects.count()
        output = StringIO()

        call_command("audit_market_access_v2", stdout=output)

        raw = output.getvalue()
        snapshot = json.loads(raw)
        self.assertFalse(snapshot["market_access_v2_enabled"])
        self.assertTrue(snapshot["v2_tables_present"])
        self.assertEqual(snapshot["v2"]["active_market_grants"], 1)
        self.assertEqual(snapshot["legacy"]["users_by_access_level"]["3"], 1)
        self.assertEqual(UserMarketGrant.objects.count(), before)
        self.assertNotIn("snapshot-private-user", raw)
        self.assertNotIn("09120000000", raw)
        self.assertNotIn("snapshot-private-password", raw)

    def test_inventory_can_run_before_v2_migrations(self):
        existing = connection.introspection.table_names()
        without_v2 = [name for name in existing if name != UserMarketGrant._meta.db_table]
        output = StringIO()

        with patch.object(connection.introspection, "table_names", return_value=without_v2):
            call_command("audit_market_access_v2", stdout=output)

        snapshot = json.loads(output.getvalue())
        self.assertFalse(snapshot["v2_tables_present"])
        self.assertNotIn("v2", snapshot)
