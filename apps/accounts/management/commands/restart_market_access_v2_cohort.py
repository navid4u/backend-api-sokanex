"""Preview or explicitly restart normal users' V2 access without deleting history."""

import json
import uuid
from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count, F, Q, Value
from django.db.models.functions import Greatest
from django.utils import timezone

from apps.accounts.market_access import market_access_v2_enabled
from apps.accounts.models import (
    TrialGrant,
    User,
    UserAccessAudit,
    UserAccessProfile,
    UserMarketGrant,
    UpgradeRequest,
)


class Command(BaseCommand):
    help = (
        "Dry-run a normal-user V2 cohort restart. --apply revokes active V2 grants, "
        "Elite and trials, while preserving trial-used markers, preferences and legacy history."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--confirm-v2-trials-remain-used", action="store_true")

    def handle(self, *args, **options):
        if options["apply"] and not options["confirm_v2_trials_remain_used"]:
            raise CommandError(
                "--apply requires --confirm-v2-trials-remain-used; revoked V2 trials "
                "remain lifetime-used and cannot be granted again."
            )
        if options["apply"] and not market_access_v2_enabled():
            raise CommandError("Enable MARKET_ACCESS_V2_ENABLED before applying a V2 cohort restart.")

        with transaction.atomic():
            # Share the campaign mutex and lock normal users before changing grants.
            if options["apply"]:
                User.objects.order_by("pk").select_for_update().values_list("pk", flat=True).first()
            normal_users = User.objects.exclude(
                Q(is_superuser=True) | Q(role__in=(User.Role.SUPER_ADMIN, User.Role.SUPPORT))
            )
            user_ids = list(
                (normal_users.select_for_update() if options["apply"] else normal_users)
                .order_by("pk").values_list("pk", flat=True)
            )
            now = timezone.now()
            grants = list(UserMarketGrant.objects.filter(user_id__in=user_ids, revoked_at__isnull=True))
            trials = list(TrialGrant.objects.filter(user_id__in=user_ids, revoked_at__isnull=True, ends_at__gt=now))
            elite_ids = set(
                UserAccessProfile.objects.filter(user_id__in=user_ids, is_elite=True)
                .values_list("user_id", flat=True)
            )
            affected_ids = {grant.user_id for grant in grants} | {trial.user_id for trial in trials} | elite_ids
            sources = Counter(grant.source for grant in grants)
            legacy = normal_users.filter(access_level__gt=1).count()
            legacy_sources = {
                row["grant_source"]: row["total"]
                for row in UpgradeRequest.objects.filter(
                    user_id__in=user_ids, status=UpgradeRequest.Status.APPROVED
                ).values("grant_source").annotate(total=Count("pk"))
            }
            report = {
                "mode": "apply" if options["apply"] else "dry_run",
                "normal_users": len(user_ids),
                "excluded_special_users": User.objects.count() - len(user_ids),
                "users_with_legacy_level_above_1": legacy,
                "legacy_approved_requests_by_source": dict(sorted(legacy_sources.items())),
                "active_v2_grants_to_revoke": len(grants),
                "active_v2_grants_by_source": dict(sorted(sources.items())),
                "active_v2_trials_to_revoke": len(trials),
                "elite_flags_to_clear": len(elite_ids),
                "users_to_audit": len(affected_ids),
                "v2_trial_reuse_policy": "TrialGrant rows remain; one lifetime use is still consumed.",
                "legacy_policy": "Legacy access levels and approval history remain stored; V2 ignores them.",
            }
            if options["apply"] and affected_ids:
                before = {
                    user_id: {
                        "grant_ids": [grant.pk for grant in grants if grant.user_id == user_id],
                        "active_trial": any(trial.user_id == user_id for trial in trials),
                        "elite": user_id in elite_ids,
                    }
                    for user_id in affected_ids
                }
                UserMarketGrant.objects.filter(pk__in=[grant.pk for grant in grants]).update(
                    revoked_at=Greatest(F("granted_at"), Value(now))
                )
                TrialGrant.objects.filter(pk__in=[trial.pk for trial in trials]).update(revoked_at=now)
                UserAccessProfile.objects.filter(user_id__in=elite_ids).update(
                    is_elite=False, elite_updated_at=now, elite_updated_by=None
                )
                operation_id = uuid.uuid4()
                UserAccessAudit.objects.bulk_create(
                    [UserAccessAudit(
                        user_id=user_id,
                        subject_user_id=user_id,
                        action=UserAccessAudit.Action.LEGACY_RESET,
                        before=before[user_id],
                        after={"membership_tier": "LEVEL_1", "reason": "V2_COHORT_RESTART"},
                        operation_id=operation_id,
                    ) for user_id in sorted(affected_ids)],
                    batch_size=500,
                )
                report["operation_id"] = str(operation_id)
            self.stdout.write(json.dumps(report, ensure_ascii=False, sort_keys=True))
