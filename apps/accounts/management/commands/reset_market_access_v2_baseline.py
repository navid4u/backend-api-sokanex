"""Explicit, audited reset of normal users to the V2 level-one baseline."""

import json
import uuid

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import F, Q, Value
from django.db.models.functions import Greatest
from django.utils import timezone

from apps.accounts.market_access import market_access_v2_enabled
from apps.accounts.market_trial import eligible_trial_users
from apps.accounts.models import (
    MarketAccessBaselineReset,
    TrialGrant,
    User,
    UserAccessAudit,
    UserAccessProfile,
    UserMarketGrant,
)


class Command(BaseCommand):
    RESET_KEY = "initial_v2_level_one_reset"
    help = (
        "Preview or reset every normal user to level 1, require market selection again, "
        "and void pre-reset V2 trials once, preserving their history."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--confirm-trial-history-voided", action="store_true")

    def handle(self, *args, **options):
        if options["apply"] and not options["confirm_trial_history_voided"]:
            raise CommandError(
                "--apply requires --confirm-trial-history-voided: pre-reset V2 trials "
                "will be invalidated for eligibility while their records remain stored."
            )
        if options["apply"] and not market_access_v2_enabled():
            raise CommandError("Enable MARKET_ACCESS_V2_ENABLED before applying this reset.")

        with transaction.atomic():
            if options["apply"]:
                # Share the campaign mutex; hold it until the reset commits.
                User.objects.order_by("pk").select_for_update().values_list("pk", flat=True).first()
                if MarketAccessBaselineReset.objects.filter(pk=self.RESET_KEY).exists():
                    raise CommandError("This one-time baseline reset has already been applied.")
            already_applied = MarketAccessBaselineReset.objects.filter(pk=self.RESET_KEY).exists()
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
            # Every pre-reset grant is voided for future eligibility, including expired ones.
            trials = list(
                TrialGrant.objects.filter(
                    user_id__in=user_ids, invalidated_at__isnull=True
                ).values_list("pk", "user_id", "revoked_at")
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
                | {user_id for _, user_id, _ in trials}
                | confirmed_ids
                | elite_ids
            )
            trial_used_ids = {user_id for _, user_id, _ in trials}
            active_trial_ids = set(
                TrialGrant.objects.filter(
                    pk__in=[pk for pk, _, _ in trials], revoked_at__isnull=True,
                    started_at__lte=now, ends_at__gt=now,
                ).values_list("user_id", flat=True)
            )
            report = {
                "mode": "apply" if options["apply"] else "dry_run",
                "already_applied": already_applied,
                "market_access_v2_enabled_in_this_process": market_access_v2_enabled(),
                "normal_users": len(user_ids),
                "excluded_special_users": User.objects.count() - len(user_ids),
                "legacy_levels_to_one": len(legacy_levels),
                "active_v2_grants_to_revoke": len(grants),
                "pre_reset_v2_trials_to_invalidate": len(trials),
                "market_confirmations_to_reset": len(confirmed_ids),
                "elite_flags_to_clear": len(elite_ids),
                "users_to_audit": len(affected_ids),
                "v2_trial_history_retained": TrialGrant.objects.filter(user_id__in=user_ids).count(),
                "eligible_for_future_v2_trial_after_reset": (
                    eligible_trial_users().count() if already_applied
                    else normal_users.filter(is_active=True).count()
                ),
                "legacy_trial_history_ignored": normal_users.filter(
                    gold_trial_started_at__isnull=False
                ).count(),
                "trial_policy": "Pre-reset V2 trials are retained but voided once; a future trial is lifetime-limited.",
            }
            if options["apply"]:
                operation_id = uuid.uuid4()
                UserMarketGrant.objects.filter(pk__in=[pk for pk, _ in grants]).update(
                    revoked_at=Greatest(F("granted_at"), Value(now))
                )
                TrialGrant.objects.filter(pk__in=[pk for pk, _, _ in trials]).update(invalidated_at=now)
                TrialGrant.objects.filter(
                    pk__in=[pk for pk, _, revoked_at in trials if revoked_at is None]
                ).update(revoked_at=now)
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
                                "trial_active": user_id in active_trial_ids,
                                "is_elite": user_id in elite_ids,
                            },
                            after={
                                "legacy_access_level": 1,
                                "membership_tier": "LEVEL_1",
                                "market_selection_confirmed": False,
                                "trial_active": False,
                                "trial_used": False,
                                "reason": "V2_LEVEL_ONE_BASELINE",
                            },
                        )
                        for user_id in sorted(affected_ids)
                    ),
                    batch_size=500,
                )
                MarketAccessBaselineReset.objects.create(
                    key=self.RESET_KEY, operation_id=operation_id,
                    normal_users=len(user_ids), invalidated_trials=len(trials),
                )
                report["operation_id"] = str(operation_id)
            self.stdout.write(json.dumps(report, ensure_ascii=False, sort_keys=True))
