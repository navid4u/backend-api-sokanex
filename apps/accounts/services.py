from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from .models import FinancialPersonalityAssessment, UpgradeRequest, User, UserProfile
from .personality_risk import ASSESSMENT_VERSION, calculate_result


class TrialAlreadyUsed(APIException):
    status_code = 409
    default_detail = "اشتراک آزمایشی قبلاً استفاده شده است."
    machine_code = "TRIAL_ALREADY_USED"


class LegacyGoldFlowDisabled(APIException):
    status_code = 409
    default_detail = "این مسیر اشتراک قدیمی در سیستم جدید غیرفعال است."
    default_code = "LEGACY_GOLD_FLOW_DISABLED"
    machine_code = "LEGACY_GOLD_FLOW_DISABLED"


class ProfileCompletionService:
    @staticmethod
    def status(user):
        profile, _ = UserProfile.objects.get_or_create(user=user)
        values = {
            "phone": bool(user.phone and user.is_verified),
            "first_name": bool(user.first_name.strip()),
            "last_name": bool(user.last_name.strip()),
            "email": bool(user.email.strip()),
            "birth_date": bool(profile.birth_date),
            "city": bool(profile.city.strip()),
            "education_level": bool(profile.education_level),
            "occupation": bool(profile.occupation.strip()),
            "risk_tolerance": bool(profile.risk_tolerance),
            "investment_goal": bool(profile.investment_goal),
            "preferred_markets": bool(profile.preferred_markets),
            "trading_frequency": bool(profile.trading_frequency),
        }
        missing = [name for name, completed in values.items() if not completed]
        missing_identity = [
            name for name in ("first_name", "last_name") if not values[name]
        ]
        completion = round(100 * (len(values) - len(missing)) / len(values))
        return {
            "profile_incomplete": bool(missing),
            "profile_complete": not bool(missing_identity),
            "profile_completion": completion,
            "missing_profile_fields": missing,
        }


class PremiumAccessService:
    TRIAL_DAYS = 7

    @staticmethod
    def _trial_conflict():
        return TrialAlreadyUsed()

    @classmethod
    def refresh_user_state(cls, user):
        """Start legacy level-5 trials once, and downgrade expired trials on auth."""
        from .market_access import market_access_v2_enabled

        if market_access_v2_enabled():
            return user
        if (
            user.access_level != User.AccessLevel.LEVEL_5
            or user.gold_permanent_granted_at
            or (
                user.gold_trial_started_at
                and user.gold_trial_expires_at
                and user.gold_trial_expires_at > timezone.now()
            )
        ):
            return user
        with transaction.atomic():
            locked = User.objects.select_for_update().get(pk=user.pk)
            if (
                locked.access_level == User.AccessLevel.LEVEL_5
                and not locked.gold_permanent_granted_at
            ):
                now = timezone.now()
                if locked.gold_trial_started_at is None:
                    locked.gold_trial_started_at = now
                    locked.gold_trial_expires_at = now + timedelta(days=cls.TRIAL_DAYS)
                    locked.save(update_fields=(
                        "gold_trial_started_at", "gold_trial_expires_at", "updated_at"
                    ))
                elif locked.gold_trial_expires_at and locked.gold_trial_expires_at <= now:
                    locked.access_level = User.AccessLevel.LEVEL_2
                    locked.save(update_fields=("access_level", "updated_at"))
        for field in (
            "access_level", "gold_trial_started_at", "gold_trial_expires_at",
            "gold_permanent_granted_at", "market_type", "telegram_id",
        ):
            setattr(user, field, getattr(locked, field))
        return user

    @classmethod
    @transaction.atomic
    def activate_trial(cls, user):
        from .market_access import market_access_v2_enabled

        if market_access_v2_enabled():
            raise LegacyGoldFlowDisabled()
        locked = User.objects.select_for_update().get(pk=user.pk)
        now = timezone.now()
        # An active trial is idempotent: repeated clicks return it unchanged.
        if (
            locked.access_level == User.AccessLevel.LEVEL_5
            and locked.gold_trial_started_at
            and locked.gold_trial_expires_at
            and locked.gold_trial_expires_at > now
        ):
            return locked
        # Eligibility is based on the one-time trial record, not the user's
        # current level. This lets existing level 2/3/4/5 accounts activate it.
        if (
            locked.gold_trial_started_at is not None
            or locked.gold_permanent_granted_at is not None
        ):
            raise cls._trial_conflict()
        locked.gold_trial_started_at = now
        locked.gold_trial_expires_at = now + timedelta(days=cls.TRIAL_DAYS)
        locked.access_level = User.AccessLevel.LEVEL_5
        locked.save(update_fields=(
            "gold_trial_started_at", "gold_trial_expires_at", "access_level", "updated_at"
        ))
        return cls.refresh_user_state(locked)

    @classmethod
    @transaction.atomic
    def request_permanent_gold(cls, user, market_type, message=""):
        from .market_access import market_access_v2_enabled

        if market_access_v2_enabled():
            raise LegacyGoldFlowDisabled()
        locked = User.objects.select_for_update().get(pk=user.pk)
        trial_expired = bool(
            locked.gold_trial_started_at
            and locked.gold_trial_expires_at
            and locked.gold_trial_expires_at <= timezone.now()
        )
        if locked.access_level != User.AccessLevel.LEVEL_2 or not trial_expired:
            raise ValidationError({"detail": "درخواست اشتراک دائمی فقط برای سطح ۲ مجاز است."})
        if market_type not in User.MarketType.values:
            raise ValidationError({"market_type": "بازار انتخاب‌شده معتبر نیست."})
        existing = UpgradeRequest.objects.filter(
            user=locked,
            request_type=UpgradeRequest.Type.PREMIUM,
            status=UpgradeRequest.Status.PENDING,
        ).first()
        if existing:
            return existing, False
        if UpgradeRequest.objects.filter(
            user=locked, status=UpgradeRequest.Status.PENDING
        ).exists():
            raise ValidationError({"detail": "درخواست دیگری از شما در حال بررسی است."})
        request = UpgradeRequest.objects.create(
            user=locked,
            request_type=UpgradeRequest.Type.PREMIUM,
            requested_level=User.AccessLevel.LEVEL_5,
            market_type=market_type,
            grant_source=UpgradeRequest.GrantSource.GOLD_RENEWAL_REQUEST,
            message=message.strip(),
        )
        return request, True

    @staticmethod
    def expire_trials():
        from .market_access import market_access_v2_enabled

        if market_access_v2_enabled():
            return 0
        now = timezone.now()
        return User.objects.filter(
            access_level=User.AccessLevel.LEVEL_5,
            gold_permanent_granted_at__isnull=True,
            gold_trial_started_at__isnull=False,
            gold_trial_expires_at__lte=now,
        ).update(access_level=User.AccessLevel.LEVEL_2, updated_at=now)


class FinancialPersonalityService:
    VERSION = 1
    DIMENSIONS = ("planning", "security", "discipline", "learning", "risk")
    TYPE_BY_DIMENSION = {
        "planning": FinancialPersonalityAssessment.PersonalityType.WEALTH_ARCHITECT,
        "security": FinancialPersonalityAssessment.PersonalityType.CAPITAL_GUARDIAN,
        "discipline": FinancialPersonalityAssessment.PersonalityType.DISCIPLINED_NAVIGATOR,
        "learning": FinancialPersonalityAssessment.PersonalityType.MARKET_EXPLORER,
        "risk": FinancialPersonalityAssessment.PersonalityType.OPPORTUNITY_HUNTER,
    }
    METADATA = {
        "WEALTH_ARCHITECT": {
            "title": "معمار ثروت",
            "subtitle": "آینده را با عدد، هدف و مسیر روشن می‌سازی.",
            "color": "#2563EB",
        },
        "CAPITAL_GUARDIAN": {
            "title": "نگهبان سرمایه",
            "subtitle": "حفظ سرمایه و تصمیم‌های سنجیده نقطه قوت توست.",
            "color": "#059669",
        },
        "OPPORTUNITY_HUNTER": {
            "title": "شکارچی فرصت",
            "subtitle": "فرصت‌ها را سریع می‌بینی و با جسارت ارزیابی می‌کنی.",
            "color": "#F59E0B",
        },
        "DISCIPLINED_NAVIGATOR": {
            "title": "ناوبر منضبط",
            "subtitle": "با نظم و پایبندی به مسیر، نوسان‌ها را مدیریت می‌کنی.",
            "color": "#7C3AED",
        },
        "MARKET_EXPLORER": {
            "title": "کاوشگر بازار",
            "subtitle": "یادگیری و کشف مسیرهای تازه موتور حرکت توست.",
            "color": "#0891B2",
        },
    }

    @classmethod
    def score_answers(cls, answers):
        scores = {dimension: 0 for dimension in cls.DIMENSIONS}
        option_points = {"a": 4, "b": 3, "c": 2, "d": 1}
        for answer in answers:
            question_index = answer["question_id"] - 1
            option_index = "abcd".index(answer["option_id"])
            dimension = cls.DIMENSIONS[(question_index + option_index) % len(cls.DIMENSIONS)]
            scores[dimension] += option_points[answer["option_id"]]
        winner = max(cls.DIMENSIONS, key=lambda dimension: scores[dimension])
        return scores, cls.TYPE_BY_DIMENSION[winner]

    @classmethod
    @transaction.atomic
    def submit(cls, user, answers):
        # Serialise submissions per user, including the very first submission
        # where there is no assessment row available to lock yet.
        User.objects.select_for_update().only("pk").get(pk=user.pk)
        scores, personality_type = cls.score_answers(answers)
        FinancialPersonalityAssessment.objects.select_for_update().filter(
            user=user, is_current=True
        ).update(is_current=False)
        return FinancialPersonalityAssessment.objects.create(
            user=user,
            version=cls.VERSION,
            personality_type=personality_type,
            score_security=scores["security"],
            score_planning=scores["planning"],
            score_risk=scores["risk"],
            score_discipline=scores["discipline"],
            score_learning=scores["learning"],
            answers=answers,
            started_at=timezone.now(),
            completed_at=timezone.now(),
            is_current=True,
        )

    @classmethod
    @transaction.atomic
    def submit_risk_v2(cls, user, answers):
        User.objects.select_for_update().only("pk").get(pk=user.pk)
        scores, percentages, dominant_type = calculate_result(answers)
        assets = next(
            answer["option_ids"] for answer in answers if answer["question_id"] == 2
        )
        FinancialPersonalityAssessment.objects.select_for_update().filter(
            user=user, is_current=True
        ).update(is_current=False)
        return FinancialPersonalityAssessment.objects.create(
            user=user,
            version=2,
            assessment_version=ASSESSMENT_VERSION,
            personality_type=dominant_type,
            dominant_type=dominant_type,
            dominant_percentage=percentages[
                {
                    "CAPITAL_GUARDIAN": "guardian",
                    "BALANCED_SMART": "balanced",
                    "FUTURE_GROWTH": "growth",
                    "OPPORTUNITY_SEEKER": "opportunity",
                }[dominant_type]
            ],
            answers=answers,
            asset_inventory=assets,
            raw_scores=scores,
            percentages=percentages,
            started_at=timezone.now(),
            completed_at=timezone.now(),
            is_current=True,
        )


class UserService:

    @staticmethod
    def list_users():
        return User.objects.select_related(
            "custom_role"
        ).order_by("-created_at")

    @staticmethod
    def toggle_active(user, performed_by):
        if user.pk == performed_by.pk:
            raise ValidationError(
                {
                    "user": (
                        "You cannot change your own active status."
                    )
                }
            )

        if user.is_superuser:
            raise ValidationError(
                {
                    "user": (
                        "A superuser cannot be deactivated here."
                    )
                }
            )

        user.is_active = not user.is_active

        user.save(
            update_fields=[
                "is_active",
                "updated_at",
            ]
        )

        return user

    @staticmethod
    def update_role(user, role, performed_by):
        if user.pk == performed_by.pk:
            raise ValidationError(
                {
                    "user": "You cannot change your own role."
                }
            )

        if user.is_superuser:
            raise ValidationError(
                {
                    "user": (
                        "A superuser role cannot be changed here."
                    )
                }
            )

        user.role = role

        user.save(
            update_fields=[
                "role",
                "updated_at",
            ]
        )

        return user

    @staticmethod
    def update_access_level(user, access_level):
        user.access_level = access_level
        user.save(update_fields=["access_level", "updated_at"])
        return user

    @staticmethod
    def update_custom_role(user, custom_role):
        user.custom_role = custom_role
        user.save(update_fields=["custom_role", "updated_at"])
        return user

    @staticmethod
    @transaction.atomic
    def review_upgrade_request(
        upgrade_request,
        status,
        reviewed_by,
        admin_note="",
    ):
        locked_request = UpgradeRequest.objects.select_for_update().get(
            pk=upgrade_request.pk
        )
        if locked_request.status != UpgradeRequest.Status.PENDING:
            if (
                locked_request.request_type == UpgradeRequest.Type.PREMIUM
                and locked_request.status == UpgradeRequest.Status.APPROVED
                and status == UpgradeRequest.Status.APPROVED
            ):
                return locked_request
            raise ValidationError(
                {"status": "Only pending requests can be reviewed."}
            )

        locked_request.status = status
        locked_request.admin_note = admin_note.strip()
        locked_request.reviewed_by = reviewed_by
        locked_request.reviewed_at = timezone.now()
        locked_request.save(
            update_fields=[
                "status",
                "admin_note",
                "reviewed_by",
                "reviewed_at",
                "updated_at",
            ]
        )

        if status == UpgradeRequest.Status.APPROVED:
            if locked_request.price_snapshot_irt and locked_request.hold_ledger_transaction_id:
                from apps.wallet.models import LedgerEntry, LedgerTransaction
                capture = LedgerTransaction.objects.create(
                    kind="UPGRADE_CAPTURE", metadata={"upgrade_request_id": locked_request.pk}
                )
                LedgerEntry.objects.bulk_create([
                    LedgerEntry(transaction=capture, account_code="UPGRADE_HOLD", direction=LedgerEntry.Direction.DEBIT, amount_irt=locked_request.price_snapshot_irt),
                    LedgerEntry(transaction=capture, account_code="UPGRADE_REVENUE", direction=LedgerEntry.Direction.CREDIT, amount_irt=locked_request.price_snapshot_irt),
                ])
            if (
                locked_request.request_type == UpgradeRequest.Type.PREMIUM
                and locked_request.grant_source == UpgradeRequest.GrantSource.GOLD_RENEWAL_REQUEST
            ):
                permanent_user = User.objects.select_for_update().get(pk=locked_request.user_id)
                locked_request.requested_level = User.AccessLevel.LEVEL_5
                locked_request.save(update_fields=("requested_level", "updated_at"))
                permanent_user.access_level = User.AccessLevel.LEVEL_5
                if permanent_user.gold_permanent_granted_at is None:
                    permanent_user.gold_permanent_granted_at = timezone.now()
                permanent_user.save(update_fields=(
                    "access_level", "gold_permanent_granted_at", "updated_at"
                ))
            else:
                UserService.update_access_level(
                    locked_request.user,
                    locked_request.requested_level,
                )
        elif locked_request.price_snapshot_irt and locked_request.hold_ledger_transaction_id:
            from apps.wallet.services import WalletService
            WalletService.post(
                WalletService.get_wallet(locked_request.user),
                locked_request.price_snapshot_irt, "UPGRADE_RELEASE",
                credit_wallet=True, counterparty="UPGRADE_HOLD",
                metadata={"upgrade_request_id": locked_request.pk},
            )

        return locked_request

    @staticmethod
    def get_statistics(user):
        return {
            "signals": user.signals.count(),

            "approved": user.signals.filter(
                status="approved"
            ).count(),

            "pending": user.signals.filter(
                status="pending"
            ).count(),

            "rejected": user.signals.filter(
                status="rejected"
            ).count(),
        }
