"""Read-only, aggregate inventory for a controlled market-access V2 rollout."""

import json

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.models import Count
from django.utils import timezone

from apps.accounts.models import (
    ContentSectionAccessAudit,
    ContentSectionAccessPolicy,
    MarketAccessRequest,
    TrialCampaign,
    TrialGrant,
    UpgradeRequest,
    User,
    UserAccessAudit,
    UserAccessProfile,
    UserMarketGrant,
    UserMarketPreference,
)


def _group_counts(queryset, field):
    return {
        str(row[field]): row["count"]
        for row in queryset.order_by().values(field).annotate(count=Count("pk"))
    }


class Command(BaseCommand):
    help = "Print a read-only, PII-free aggregate snapshot of legacy and V2 access state."

    def handle(self, *args, **options):
        known_tables = set(connection.introspection.table_names())
        v2_models = (
            UserAccessProfile,
            UserMarketPreference,
            UserMarketGrant,
            TrialCampaign,
            TrialGrant,
            UserAccessAudit,
            ContentSectionAccessPolicy,
            ContentSectionAccessAudit,
            MarketAccessRequest,
        )
        v2_tables_present = all(model._meta.db_table in known_tables for model in v2_models)

        snapshot = {
            "generated_at": timezone.now().isoformat(),
            "database_vendor": connection.vendor,
            "market_access_v2_enabled": bool(getattr(settings, "MARKET_ACCESS_V2_ENABLED", False)),
            "legacy": {
                "users": User.objects.count(),
                "users_by_role": _group_counts(User.objects, "role"),
                "users_by_access_level": _group_counts(User.objects, "access_level"),
                "superusers": User.objects.filter(is_superuser=True).count(),
                "legacy_gold_trials_started": User.objects.filter(gold_trial_started_at__isnull=False).count(),
                "legacy_gold_trials_active": User.objects.filter(gold_trial_expires_at__gt=timezone.now()).count(),
                "legacy_gold_permanent": User.objects.filter(gold_permanent_granted_at__isnull=False).count(),
                "upgrade_requests": UpgradeRequest.objects.count(),
                "upgrade_requests_by_type": _group_counts(UpgradeRequest.objects, "request_type"),
                "upgrade_requests_by_status": _group_counts(UpgradeRequest.objects, "status"),
            },
            "v2_tables_present": v2_tables_present,
        }
        if v2_tables_present:
            snapshot["v2"] = {
                "profiles": UserAccessProfile.objects.count(),
                "preferences": UserMarketPreference.objects.count(),
                "active_market_grants": UserMarketGrant.objects.filter(revoked_at__isnull=True).count(),
                "revoked_market_grants": UserMarketGrant.objects.filter(revoked_at__isnull=False).count(),
                "trial_campaigns": TrialCampaign.objects.count(),
                "trial_grants": TrialGrant.objects.count(),
                "access_audits": UserAccessAudit.objects.count(),
                "content_policies": ContentSectionAccessPolicy.objects.count(),
                "content_policy_audits": ContentSectionAccessAudit.objects.count(),
                "market_access_requests": MarketAccessRequest.objects.count(),
                "market_access_requests_by_status": _group_counts(MarketAccessRequest.objects, "status"),
            }
        self.stdout.write(json.dumps(snapshot, ensure_ascii=False, sort_keys=True))
