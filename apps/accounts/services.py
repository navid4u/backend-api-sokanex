from rest_framework.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import FinancialPersonalityAssessment, UpgradeRequest, User, UserProfile


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
        completion = round(100 * (len(values) - len(missing)) / len(values))
        return {
            "profile_incomplete": bool(missing),
            "profile_completion": completion,
            "missing_profile_fields": missing,
        }


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
