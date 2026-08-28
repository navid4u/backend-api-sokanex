import hashlib
import hmac
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import APIException, Throttled, ValidationError

from apps.activity.services import ActivityService
from common.sms import PayamitoSMSService, SMSProviderError, render_sms_template

from .models import OTPChallenge, User, UserProfile


class OTPProviderError(APIException):
    status_code = 503
    default_detail = "Verification-code delivery is temporarily unavailable."
    default_code = "otp_provider_unavailable"


class RegistrationOTPError(APIException):
    status_code = 400

    def __init__(self, message, machine_code="INVALID_OTP", status_code=None):
        self.machine_code = machine_code
        if status_code is not None:
            self.status_code = status_code
        super().__init__({"code": [message]}, code=machine_code.lower())


class PayamitoService:
    @classmethod
    def send_otp(cls, phone, code):
        try:
            result = PayamitoSMSService.send(
                phone,
                render_sms_template(settings.PAYAMITO_OTP_MESSAGE_TEMPLATE, code=code),
            )
        except SMSProviderError as exc:
            raise OTPProviderError() from exc
        return {"value": result["message_id"], "status": result["status"]}


class OTPService:
    lifetime_seconds = 120
    cooldown_seconds = 120
    window_minutes = 10
    max_requests = 3
    max_attempts = 5

    @staticmethod
    def _digest(phone, code, salt):
        message = f"{phone}:{code}:{salt}".encode()
        return hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).hexdigest()

    @classmethod
    def request_code(
        cls,
        phone,
        request,
        purpose=OTPChallenge.Purpose.LOGIN,
        cooldown_seconds=None,
    ):
        now = timezone.now()
        cooldown = cls.cooldown_seconds if cooldown_seconds is None else cooldown_seconds
        ip = ActivityService.client_ip(request)
        window = now - timedelta(minutes=cls.window_minutes)
        with transaction.atomic():
            purpose_challenges = OTPChallenge.objects.filter(phone=phone, purpose=purpose)
            latest = purpose_challenges.select_for_update().first()
            if latest and latest.created_at > now - timedelta(seconds=cooldown):
                wait = cooldown - int((now - latest.created_at).total_seconds())
                raise Throttled(wait=max(wait, 1), detail="Please wait before requesting another code.")
            if purpose_challenges.filter(created_at__gte=window).count() >= cls.max_requests:
                raise Throttled(wait=cooldown, detail="Too many verification-code requests.")
            if ip and OTPChallenge.objects.filter(
                request_ip=ip, purpose=purpose, created_at__gte=window
            ).count() >= cls.max_requests:
                raise Throttled(wait=cooldown, detail="Too many requests from this network.")

            code = f"{secrets.randbelow(10000):04d}"
            salt = secrets.token_hex(32)
            challenge = OTPChallenge.objects.create(
                phone=phone,
                purpose=purpose,
                salt=salt,
                code_digest=cls._digest(phone, code, salt),
                request_ip=ip,
                expires_at=now + timedelta(seconds=cls.lifetime_seconds),
            )
        try:
            PayamitoService.send_otp(phone, code)
        except Exception:
            OTPChallenge.objects.filter(pk=challenge.pk).update(locked_at=timezone.now())
            raise
        return challenge

    @classmethod
    def verify_code(cls, phone, code, purpose=OTPChallenge.Purpose.LOGIN):
        invalid = False
        challenge = None
        with transaction.atomic():
            challenge = OTPChallenge.objects.select_for_update().filter(
                phone=phone, purpose=purpose
            ).first()
            now = timezone.now()
            if not challenge or not challenge.is_usable:
                invalid = True
            else:
                valid = hmac.compare_digest(
                    challenge.code_digest,
                    cls._digest(phone, code, challenge.salt),
                )
                if not valid:
                    challenge.attempts += 1
                    if challenge.attempts >= cls.max_attempts:
                        challenge.locked_at = now
                    challenge.save(update_fields=["attempts", "locked_at"])
                    invalid = True
                else:
                    challenge.consumed_at = now
                    challenge.save(update_fields=["consumed_at"])
        if invalid:
            raise ValidationError({"code": "The verification code is invalid or expired."})
        return challenge

    @classmethod
    def verify_registration_login(cls, phone, code):
        invalid = False
        account_error = None
        user = None
        created = False
        with transaction.atomic():
            challenge = OTPChallenge.objects.select_for_update().filter(
                phone=phone,
                purpose=OTPChallenge.Purpose.REGISTRATION_LOGIN,
            ).first()
            now = timezone.now()
            if not challenge or not challenge.is_usable:
                invalid = True
            elif not hmac.compare_digest(
                challenge.code_digest,
                cls._digest(phone, code, challenge.salt),
            ):
                challenge.attempts += 1
                if challenge.attempts >= cls.max_attempts:
                    challenge.locked_at = now
                challenge.save(update_fields=["attempts", "locked_at"])
                invalid = True
            else:
                challenge.consumed_at = now
                challenge.save(update_fields=["consumed_at"])
                matches = list(
                    User.objects.select_for_update().filter(
                        Q(phone=phone) | Q(username=phone)
                    ).distinct()[:2]
                )
                if len(matches) > 1:
                    account_error = RegistrationOTPError(
                        "برای این شماره تعارض حساب وجود دارد؛ با پشتیبانی تماس بگیرید.",
                        "PHONE_CONFLICT",
                        409,
                    )
                elif matches:
                    user = matches[0]
                    if not user.is_active:
                        account_error = RegistrationOTPError(
                            "این حساب غیرفعال یا مسدود است.",
                            "ACCOUNT_INACTIVE",
                            403,
                        )
                    else:
                        update_fields = []
                        if not user.phone:
                            user.phone = phone
                            update_fields.append("phone")
                        if not user.is_verified:
                            user.is_verified = True
                            update_fields.append("is_verified")
                        if update_fields:
                            user.save(update_fields=[*update_fields, "updated_at"])
                else:
                    try:
                        with transaction.atomic():
                            user = User.objects.create(
                                username=phone,
                                phone=phone,
                                role=User.Role.USER,
                                access_level=User.AccessLevel.LEVEL_1,
                                is_active=True,
                                is_verified=True,
                            )
                            user.set_unusable_password()
                            user.save(update_fields=["password", "updated_at"])
                            UserProfile.objects.get_or_create(user=user)
                            created = True
                    except IntegrityError:
                        user = User.objects.select_for_update().filter(phone=phone).first()
                        if not user:
                            account_error = RegistrationOTPError(
                                "برای این شماره تعارض حساب وجود دارد؛ با پشتیبانی تماس بگیرید.",
                                "PHONE_CONFLICT",
                                409,
                            )
        if invalid:
            raise RegistrationOTPError("کد تأیید نامعتبر یا منقضی شده است.")
        if account_error:
            raise account_error
        return user, created
