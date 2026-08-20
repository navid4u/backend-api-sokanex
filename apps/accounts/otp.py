import hashlib
import hmac
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, Throttled, ValidationError

from apps.activity.services import ActivityService
from common.sms import PayamitoPatternService, SMSProviderError

from .models import OTPChallenge


class OTPProviderError(APIException):
    status_code = 503
    default_detail = "Verification-code delivery is temporarily unavailable."
    default_code = "otp_provider_unavailable"


class PayamitoService:
    @classmethod
    def send_otp(cls, phone, code):
        try:
            result = PayamitoPatternService.send(
                phone, settings.PAYAMITO_OTP_BODY_ID, [code]
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
    def request_code(cls, phone, request):
        now = timezone.now()
        ip = ActivityService.client_ip(request)
        window = now - timedelta(minutes=cls.window_minutes)
        with transaction.atomic():
            latest = OTPChallenge.objects.select_for_update().filter(phone=phone).first()
            if latest and latest.created_at > now - timedelta(seconds=cls.cooldown_seconds):
                wait = cls.cooldown_seconds - int((now - latest.created_at).total_seconds())
                raise Throttled(wait=max(wait, 1), detail="Please wait before requesting another code.")
            if OTPChallenge.objects.filter(phone=phone, created_at__gte=window).count() >= cls.max_requests:
                raise Throttled(wait=cls.cooldown_seconds, detail="Too many verification-code requests.")
            if ip and OTPChallenge.objects.filter(request_ip=ip, created_at__gte=window).count() >= cls.max_requests:
                raise Throttled(wait=cls.cooldown_seconds, detail="Too many requests from this network.")

            code = f"{secrets.randbelow(10000):04d}"
            salt = secrets.token_hex(32)
            challenge = OTPChallenge.objects.create(
                phone=phone,
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
    def verify_code(cls, phone, code):
        invalid = False
        challenge = None
        with transaction.atomic():
            challenge = OTPChallenge.objects.select_for_update().filter(phone=phone).first()
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
