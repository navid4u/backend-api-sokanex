"""Explicit, audited reset of normal users to the V2 level-one baseline."""

import json
import uuid

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import F, Q, Value
from django.db.models.functions import Greatest
from django.utils import timezone

from apps.accounts.market_access import market_access_v2_enabled
from apps.accounts.models import (
    TrialGrant,
    User,
    UserAccessAudit,
    UserAccessProfile,
    UserMarketGrant,
)


class Command(BaseCommand):
    help = (
        "Preview or reset every normal user to level 1, require market selection again, "
        "and revoke current V2 access. Trial history remains lifetime-used."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--confirm-trials-remain-used", action="store_true")

    def handle(self, *args, **options):
        if options["apply"] and not options["confirm_trials_remain_used"]:
            raise CommandError(
                "--apply requires --confirm-trials-remain-used: existing V2 TrialGrant "
                "records remain lifetime-used after their active access is revoked."
            )
        if options["apply"] and not market_access_v2_enabled():
            raise CommandError("Enable MARKET_ACCESS_V2_ENABLED before applying this reset.")

        with transaction.atomic():
            if options["apply"]:
                # Share the campaign mutex; hold it until the reset commits.
                User.objects.order_by("pk").select_for_update().values_list("pk", flat=True).first()
            normal_users = User.objects.exclude(
                Q(is_superuser=True) | Q(role__in=(User.Role.SUPER_ADMIN, User.Role.SUPPORT))
            )
            user_ids = list(
                (normal_users.select_for_update() if options["apply"] else normal_users)
                .order_by("pk").values_list("pk", flat=True)
            )
            now = timezone.now()
            legacy_levels = dict(
                normal_users.exclude(access_level=User.AccessLevel.LEVEL_1)
                .values_list("pk", "access_level")
            )
            grants = list(
                UserMarketGrant.objects.filter(user_id__in=user_ids, revoked_at__isnull=True)
                .values_list("pk", "user_id")
            )
            # Revoke active and scheduled grants, not historical expired rows.
            trials = list(
                TrialGrant.objects.filter(
                    user_id__in=user_ids, revoked_at__isnull=True, ends_at__gt=now
                ).values_list("pk", "user_id")
            )
            profiles = list(
                UserAccessProfile.objects.filter(user_id__in=user_ids)
                .filter(Q(market_selection_confirmed_at__isnull=False) | Q(is_elite=True))
                .values_list("user_id", "market_selection_confirmed_at", "is_elite")
            )
            confirmed_ids = {user_id for user_id, confirmed_at, _ in profiles if confirmed_at}
            elite_ids = {user_id for user_id, _, is_elite in profiles if is_elite}
            affected_ids = (
                set(legacy_levels)
                | {user_id for _, user_id in grants}
                | {user_id for _, user_id in trials}
                | confirmed_ids
                | elite_ids
            )
            trial_used_ids = set(
                TrialGrant.objects.filter(user_id__in=user_ids).values_list("user_id", flat=True)
            )
            report = {
                "mode": "apply" if options["apply"] else "dry_run",
                "market_access_v2_enabled_in_this_process": market_access_v2_enabled(),
                "normal_users": len(user_ids),
                "excluded_special_users": User.objects.count() - len(user_ids),
                "legacy_levels_to_one": len(legacy_levels),
                "active_v2_grants_to_revoke": len(grants),
                "active_or_scheduled_v2_trials_to_revoke": len(trials),
                "market_confirmations_to_reset": len(confirmed_ids),
                "elite_flags_to_clear": len(elite_ids),
                "users_to_audit": len(affected_ids),
                "v2_trial_history_retained": len(trial_used_ids),
                "eligible_for_future_v2_trial_after_reset": normal_users.filter(
                    is_active=True, trial_grant_v2__isnull=True
                ).count(),
                "legacy_trial_history_ignored": normal_users.filter(
                    gold_trial_started_at__isnull=False
                ).count(),
                "trial_policy": "Existing V2 TrialGrant records remain lifetime-used; legacy trials do not count.",
            }
            if options["apply"] and affected_ids:
                operation_id = uuid.uuid4()
                UserMarketGrant.objects.filter(pk__in=[pk for pk, _ in grants]).update(
                    revoked_at=Greatest(F("granted_at"), Value(now))
                )
                TrialGrant.objects.filter(pk__in=[pk for pk, _ in trials]).update(revoked_at=now)
                UserAccessProfile.objects.filter(user_id__in=confirmed_ids).update(
                    market_selection_confirmed_at=None
                )
                UserAccessProfile.objects.filter(user_id__in=elite_ids).update(
                    is_elite=False, elite_updated_at=now, elite_updated_by=None
                )
                normal_users.filter(pk__in=legacy_levels).update(
                    access_level=User.AccessLevel.LEVEL_1, updated_at=now
                )
                granted_ids = {user_id for _, user_id in grants}
                trial_ids = {user_id for _, user_id in trials}
                UserAccessAudit.objects.bulk_create(
                    (
                        UserAccessAudit(
                            user_id=user_id,
                            subject_user_id=user_id,
                            action=UserAccessAudit.Action.LEGACY_RESET,
                            operation_id=operation_id,
                            before={
                                "legacy_access_level": legacy_levels.get(user_id, 1),
                                "market_selection_confirmed": user_id in confirmed_ids,
                                "had_market_grant": user_id in granted_ids,
                                "trial_active": user_id in trial_ids,
                                "is_elite": user_id in elite_ids,
                            },
                            after={
                                "legacy_access_level": 1,
                                "membership_tier": "LEVEL_1",
                                "market_selection_confirmed": False,
                                "trial_active": False,
                                "trial_used": user_id in trial_used_ids,
                                "reason": "V2_LEVEL_ONE_BASELINE",
                            },
                        )
                        for user_id in sorted(affected_ids)
                    ),
                    batch_size=500,
                )
                report["operation_id"] = str(operation_id)
            self.stdout.write(json.dumps(report, ensure_ascii=False, sort_keys=True))
