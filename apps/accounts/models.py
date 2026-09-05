from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify
from common.phone import normalize_iran_phone, validate_iran_phone


class User(AbstractUser):

    class Role(models.TextChoices):
        SUPER_ADMIN = "SUPER_ADMIN", "Super Admin"
        ADMIN = "ADMIN", "Admin"
        TRADER = "TRADER", "Trader"
        EMPLOYEE = "EMPLOYEE", "Employee"
        SUPPORT = "SUPPORT", "Support"
        USER = "USER", "User"

    class AccessLevel(models.IntegerChoices):
        LEVEL_1 = 1, "Level 1"
        LEVEL_2 = 2, "Level 2"
        LEVEL_3 = 3, "Level 3"
        LEVEL_4 = 4, "Level 4"
        LEVEL_5 = 5, "Level 5"

    class Permission(models.TextChoices):
        CONTENT_MANAGE = "CONTENT_MANAGE", "Manage content"
        CONTENT_VIEW_ALL = "CONTENT_VIEW_ALL", "View all content levels"
        SIGNAL_SUBMIT = "SIGNAL_SUBMIT", "Submit signals"
        SIGNAL_REVIEW = "SIGNAL_REVIEW", "Review signals"
        ACADEMY_TEACH = "ACADEMY_TEACH", "Create and teach courses"
        ACADEMY_MANAGE = "ACADEMY_MANAGE", "Manage all academy courses"
        LANDING_MANAGE = "LANDING_MANAGE", "Manage landing page"
        USER_MANAGE = "USER_MANAGE", "Manage users"
        ROLE_MANAGE = "ROLE_MANAGE", "Manage custom roles"
        INTERNAL_ANALYSIS_MANAGE = "INTERNAL_ANALYSIS_MANAGE", "Manage internal analysis"
        SUPPORT_MANAGE = "SUPPORT_MANAGE", "Manage support conversations"
        PLATFORM_SETTINGS_MANAGE = "PLATFORM_SETTINGS_MANAGE", "Manage platform settings"
        AI_ASSISTANT_MANAGE = "can_manage_ai_assistant", "Manage AI assistant"

    phone = models.CharField(
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        validators=[validate_iran_phone],
    )

    avatar = models.ImageField(
        upload_to="avatars/",
        null=True,
        blank=True
    )

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.USER
    )

    access_level = models.PositiveSmallIntegerField(
        default=AccessLevel.LEVEL_1,
        choices=AccessLevel.choices,
    )

    custom_role = models.ForeignKey(
        "PlatformRole",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
    )

    is_verified = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.username

    def save(self, *args, **kwargs):
        if self.phone:
            self.phone = normalize_iran_phone(self.phone)
        super().save(*args, **kwargs)

    def has_platform_permission(self, permission):
        if self.is_superuser or self.role == self.Role.SUPER_ADMIN:
            return True

        # SUPPORT is a fixed, isolated role. Custom roles must never expand it.
        if self.role == self.Role.SUPPORT:
            return permission == self.Permission.SUPPORT_MANAGE

        system_permissions = {
            self.Role.ADMIN: {
                self.Permission.CONTENT_MANAGE,
                self.Permission.CONTENT_VIEW_ALL,
                self.Permission.SIGNAL_REVIEW,
                self.Permission.SIGNAL_SUBMIT,
                self.Permission.ACADEMY_MANAGE,
                self.Permission.LANDING_MANAGE,
                self.Permission.USER_MANAGE,
                self.Permission.ROLE_MANAGE,
            },
            self.Role.EMPLOYEE: {
                self.Permission.CONTENT_MANAGE,
                self.Permission.CONTENT_VIEW_ALL,
                self.Permission.SIGNAL_REVIEW,
            },
            self.Role.TRADER: {
                self.Permission.SIGNAL_SUBMIT,
            },
        }

        if permission in system_permissions.get(self.role, set()):
            return True

        return bool(
            self.custom_role
            and self.custom_role.is_active
            and permission in self.custom_role.permissions
        )


class PlatformRole(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    permissions = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_platform_roles",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name, allow_unicode=True) or "role"
            slug = base_slug
            counter = 2
            while PlatformRole.objects.filter(slug=slug).exclude(
                pk=self.pk
            ).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)


class UpgradeRequest(models.Model):

    class Type(models.TextChoices):
        UPGRADE = "UPGRADE", "Level upgrade"
        PREMIUM = "PREMIUM", "Premium subscription"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="upgrade_requests",
    )
    request_type = models.CharField(
        max_length=20,
        choices=Type.choices,
        default=Type.UPGRADE,
    )
    requested_level = models.PositiveSmallIntegerField(
        choices=[(level, f"Level {level}") for level in range(2, 6)],
    )
    plan = models.ForeignKey("wallet.UpgradePlan", null=True, blank=True, on_delete=models.PROTECT)
    price_snapshot_irt = models.PositiveBigIntegerField(default=0)
    price_snapshot_usd = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    purchase_idempotency_key = models.CharField(max_length=120, null=True, blank=True)
    usd_ledger_entry = models.ForeignKey(
        "wallet.UsdLedgerEntry",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="premium_upgrade_requests",
    )
    hold_ledger_transaction = models.ForeignKey(
        "wallet.LedgerTransaction", null=True, blank=True, on_delete=models.PROTECT,
        related_name="upgrade_holds",
    )
    message = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    admin_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_upgrade_requests",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(status="PENDING"),
                name="one_pending_upgrade_request_per_user",
            ),
            models.UniqueConstraint(
                fields=["user", "purchase_idempotency_key"],
                condition=Q(purchase_idempotency_key__isnull=False),
                name="unique_premium_purchase_key_per_user",
            ),
        ]

    def __str__(self):
        return (
            f"{self.user} - {self.request_type} "
            f"to level {self.requested_level}"
        )


class UserProfile(models.Model):

    class Gender(models.TextChoices):
        MALE = "MALE", "Male"
        FEMALE = "FEMALE", "Female"
        OTHER = "OTHER", "Other"
        PREFER_NOT_TO_SAY = "PREFER_NOT_TO_SAY", "Prefer not to say"

    class MaritalStatus(models.TextChoices):
        SINGLE = "SINGLE", "Single"
        MARRIED = "MARRIED", "Married"
        DIVORCED = "DIVORCED", "Divorced"
        WIDOWED = "WIDOWED", "Widowed"
        PREFER_NOT_TO_SAY = "PREFER_NOT_TO_SAY", "Prefer not to say"

    class EducationLevel(models.TextChoices):
        HIGH_SCHOOL = "HIGH_SCHOOL", "High school"
        ASSOCIATE = "ASSOCIATE", "Associate"
        BACHELOR = "BACHELOR", "Bachelor"
        MASTER = "MASTER", "Master"
        DOCTORATE = "DOCTORATE", "Doctorate"
        OTHER = "OTHER", "Other"

    class IncomeRange(models.TextChoices):
        NO_INCOME = "NO_INCOME", "No income"
        UNDER_10M_IRT = "UNDER_10M_IRT", "Under 10M IRT"
        FROM_10M_TO_30M_IRT = "10M_30M_IRT", "10M to 30M IRT"
        FROM_30M_TO_60M_IRT = "30M_60M_IRT", "30M to 60M IRT"
        FROM_60M_TO_100M_IRT = "60M_100M_IRT", "60M to 100M IRT"
        OVER_100M_IRT = "OVER_100M_IRT", "Over 100M IRT"
        UNDER_500 = "UNDER_500", "Legacy: under 500"
        FROM_500_TO_1000 = "500_1000", "Legacy: 500 to 1,000"
        FROM_1000_TO_3000 = "1000_3000", "Legacy: 1,000 to 3,000"
        FROM_3000_TO_5000 = "3000_5000", "Legacy: 3,000 to 5,000"
        FROM_5000_TO_10000 = "5000_10000", "Legacy: 5,000 to 10,000"
        OVER_10000 = "OVER_10000", "Legacy: over 10,000"
        PREFER_NOT_TO_SAY = "PREFER_NOT_TO_SAY", "Prefer not to say"

    class RiskTolerance(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"

    class TradingFrequency(models.TextChoices):
        NEVER = "NEVER", "Never"
        RARELY = "RARELY", "Rarely"
        WEEKLY = "WEEKLY", "Weekly"
        DAILY = "DAILY", "Daily"
        MULTIPLE_DAILY = "MULTIPLE_DAILY", "Multiple times daily"

    class PreferredLearningTime(models.TextChoices):
        MORNING = "MORNING", "Morning"
        AFTERNOON = "AFTERNOON", "Afternoon"
        EVENING = "EVENING", "Evening"
        NIGHT = "NIGHT", "Night"
        FLEXIBLE = "FLEXIBLE", "Flexible"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile_details",
    )
    bio = models.TextField(blank=True)
    birth_date = models.DateField(null=True, blank=True)
    gender = models.CharField(
        max_length=30,
        choices=Gender.choices,
        blank=True,
    )
    country = models.CharField(max_length=2, default="IR")
    city = models.CharField(max_length=100, blank=True)
    address = models.CharField(max_length=500, blank=True)
    postal_code = models.CharField(max_length=30, blank=True)
    marital_status = models.CharField(
        max_length=30,
        choices=MaritalStatus.choices,
        blank=True,
    )
    education_level = models.CharField(
        max_length=30,
        choices=EducationLevel.choices,
        blank=True,
    )
    occupation = models.CharField(max_length=150, blank=True)
    job_title = models.CharField(max_length=150, blank=True)
    company_name = models.CharField(max_length=150, blank=True)
    monthly_income_range = models.CharField(
        max_length=30,
        choices=IncomeRange.choices,
        blank=True,
    )
    income_currency = models.CharField(max_length=10, default="IRT")
    income_sources = models.JSONField(default=list, blank=True)
    financial_dependents = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
    )
    trading_experience_years = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
    )
    risk_tolerance = models.CharField(
        max_length=20,
        choices=RiskTolerance.choices,
        blank=True,
    )
    investment_goal = models.TextField(blank=True)
    preferred_markets = models.JSONField(default=list, blank=True)
    trading_frequency = models.CharField(
        max_length=30,
        choices=TradingFrequency.choices,
        blank=True,
    )
    daily_free_time_minutes = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
    )
    learning_hours_weekly = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
    )
    preferred_learning_time = models.CharField(
        max_length=20,
        choices=PreferredLearningTime.choices,
        blank=True,
    )
    exercise_days_per_week = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
    )
    sleep_hours_average = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        null=True,
        blank=True,
    )
    interests = models.JSONField(default=list, blank=True)
    habits = models.JSONField(default=dict, blank=True)
    onboarding_answers = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(exercise_days_per_week__isnull=True)
                    | Q(exercise_days_per_week__lte=7)
                ),
                name="profile_exercise_days_max_7",
            ),
            models.CheckConstraint(
                condition=(
                    Q(sleep_hours_average__isnull=True)
                    | Q(sleep_hours_average__lte=24)
                ),
                name="profile_sleep_hours_max_24",
            ),
            models.CheckConstraint(
                condition=(
                    Q(daily_free_time_minutes__isnull=True)
                    | Q(daily_free_time_minutes__lte=1440)
                ),
                name="profile_free_time_max_1440",
            ),
            models.CheckConstraint(
                condition=(
                    Q(learning_hours_weekly__isnull=True)
                    | Q(learning_hours_weekly__lte=168)
                ),
                name="profile_learning_hours_max_168",
            ),
        ]

    def __str__(self):
        return f"Profile details for {self.user}"


class SecuritySettings(models.Model):
    max_active_devices = models.PositiveSmallIntegerField(default=5)
    session_lifetime_days = models.PositiveSmallIntegerField(default=30)
    notify_new_login = models.BooleanField(default=True)
    require_verified_email_for_sensitive_actions = models.BooleanField(default=False)
    maintenance_message = models.CharField(max_length=300, blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="security_settings_updates",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Security settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Platform security settings"


class UserDevice(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="devices",
    )
    device_id = models.CharField(max_length=64)
    name = models.CharField(max_length=150, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    refresh_jti = models.CharField(max_length=255, blank=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_seen_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "device_id"],
                name="unique_user_device_id",
            )
        ]
        indexes = [models.Index(fields=["user", "revoked_at", "-last_seen_at"])]

    @property
    def is_active(self):
        return self.revoked_at is None

    def __str__(self):
        return self.name or self.device_id


class Badge(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True, allow_unicode=True)
    description = models.TextField(blank=True)
    icon = models.ImageField(upload_to="badges/icons/", null=True, blank=True)
    color = models.CharField(max_length=20, default="#2563EB")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name, allow_unicode=True) or "badge"
            candidate, counter = base, 2
            while Badge.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                candidate = f"{base}-{counter}"
                counter += 1
            self.slug = candidate
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class UserBadge(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="earned_badges",
    )
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE, related_name="awards")
    note = models.CharField(max_length=300, blank=True)
    awarded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="awarded_badges",
    )
    awarded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-awarded_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "badge"], name="unique_badge_per_user")
        ]

    def __str__(self):
        return f"{self.user} - {self.badge}"


class OTPChallenge(models.Model):
    class Purpose(models.TextChoices):
        LOGIN = "LOGIN", "Login"
        REGISTRATION_LOGIN = "REGISTRATION_LOGIN", "Registration or login"

    phone = models.CharField(max_length=11, db_index=True)
    purpose = models.CharField(max_length=24, choices=Purpose.choices, default=Purpose.LOGIN)
    code_digest = models.CharField(max_length=64)
    salt = models.CharField(max_length=64)
    request_ip = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["phone", "-created_at"]),
            models.Index(fields=["phone", "purpose", "-created_at"]),
        ]

    @property
    def is_usable(self):
        from django.utils import timezone
        return (
            bool(self.sent_at)
            and not self.consumed_at
            and not self.locked_at
            and self.expires_at > timezone.now()
        )


class FinancialPersonalityAssessment(models.Model):
    class PersonalityType(models.TextChoices):
        WEALTH_ARCHITECT = "WEALTH_ARCHITECT", "معمار ثروت"
        CAPITAL_GUARDIAN = "CAPITAL_GUARDIAN", "نگهبان سرمایه"
        OPPORTUNITY_HUNTER = "OPPORTUNITY_HUNTER", "شکارچی فرصت"
        DISCIPLINED_NAVIGATOR = "DISCIPLINED_NAVIGATOR", "ناوبر منضبط"
        MARKET_EXPLORER = "MARKET_EXPLORER", "کاوشگر بازار"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="financial_personality_assessments",
    )
    version = models.PositiveSmallIntegerField(default=1)
    personality_type = models.CharField(max_length=30, choices=PersonalityType.choices)
    score_security = models.PositiveSmallIntegerField(default=0)
    score_planning = models.PositiveSmallIntegerField(default=0)
    score_risk = models.PositiveSmallIntegerField(default=0)
    score_discipline = models.PositiveSmallIntegerField(default=0)
    score_learning = models.PositiveSmallIntegerField(default=0)
    answers = models.JSONField(default=list)
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(default=timezone.now)
    is_current = models.BooleanField(default=True)

    class Meta:
        ordering = ["-completed_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(is_current=True),
                name="one_current_financial_personality_per_user",
            )
        ]
        indexes = [models.Index(fields=["user", "-completed_at"])]


class FinancialPersonalityAuditLog(models.Model):
    assessment = models.ForeignKey(
        FinancialPersonalityAssessment,
        on_delete=models.PROTECT,
        related_name="audit_logs",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="financial_personality_audits",
    )
    changes = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class CrmContactSync(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SYNCED = "synced", "Synced"
        FAILED = "failed", "Failed"
        NEEDS_REVIEW = "needs_review", "Needs review"
        DEAD_LETTER = "dead_letter", "Dead letter"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="crm_contact_sync",
    )
    remote_ulid = models.CharField(max_length=64, blank=True)
    phone_e164 = models.CharField(max_length=20, blank=True, db_index=True)
    payload_hash = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.CharField(max_length=500, blank=True)
    last_response_code = models.CharField(max_length=30, blank=True)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]
        indexes = [models.Index(fields=["status", "next_retry_at"])]


class BrokerConnection(models.Model):
    class Status(models.TextChoices):
        NOT_STARTED = "not_started", "Not started"
        PENDING = "pending", "Pending"
        REJECTED = "rejected", "Rejected"
        CONNECTED = "connected", "Connected"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="broker_connection"
    )
    broker_name = models.CharField(max_length=150)
    account_number = models.CharField(max_length=100)
    referral_code = models.CharField(max_length=100, blank=True)
    document = models.FileField(upload_to="broker-connections/%Y/%m/")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    rejection_reason = models.TextField(blank=True)
    balance = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    equity = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    currency = models.CharField(max_length=10, default="USD")
    chart = models.JSONField(default=list, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reviewed_broker_connections",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"{self.user} - {self.broker_name} ({self.status})"
