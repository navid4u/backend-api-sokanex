import hashlib
import json
import logging
from datetime import datetime, time, timedelta, timezone as dt_timezone
from urllib import error, request

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from common.phone import normalize_iran_phone
from .models import CrmContactSync, UserProfile


logger = logging.getLogger(__name__)


class CrmContactSyncService:
    @staticmethod
    def normalize_phone(value):
        return "98" + normalize_iran_phone(value)[1:]

    @classmethod
    def build_payload(cls, user):
        profile = UserProfile.objects.filter(user=user).first()
        payload = {
            "name": user.last_name.strip(),
            "firstname": user.first_name.strip(),
            "phone_number": cls.normalize_phone(user.phone),
        }
        if user.email:
            payload["email"] = user.email.strip()
        if profile:
            gender = {
                UserProfile.Gender.MALE: "مرد",
                UserProfile.Gender.FEMALE: "زن",
            }.get(profile.gender)
            if gender:
                payload["gender"] = gender
            if profile.birth_date:
                birth = datetime.combine(profile.birth_date, time.min, tzinfo=dt_timezone.utc)
                payload["birthday"] = int(birth.timestamp())
            if profile.address:
                payload["address"] = profile.address.strip()
        operator = str(settings.CRM_FOLLOWUP_OPERATOR).strip()
        if operator:
            payload["followUp_operator"] = operator
        return payload

    @staticmethod
    def payload_hash(payload):
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @classmethod
    def queue_user(cls, user_id):
        if not settings.CRM_ENABLED:
            return None
        from .models import User

        user = User.objects.filter(pk=user_id).first()
        if not user or not user.phone or not user.first_name.strip() or not user.last_name.strip():
            return None
        try:
            payload = cls.build_payload(user)
        except ValidationError:
            sync, _ = CrmContactSync.objects.get_or_create(user=user)
            sync.status = CrmContactSync.Status.NEEDS_REVIEW
            sync.last_error = "شماره همراه برای CRM معتبر نیست."
            sync.save(update_fields=("status", "last_error", "updated_at"))
            return sync

        digest = cls.payload_hash(payload)
        sync, _ = CrmContactSync.objects.get_or_create(
            user=user,
            defaults={"phone_e164": payload["phone_number"], "payload_hash": digest},
        )
        if sync.remote_ulid:
            if sync.payload_hash != digest:
                sync.status = CrmContactSync.Status.NEEDS_REVIEW
                sync.last_error = "اطلاعات مخاطب تغییر کرده و endpoint ویرایش CRM تعریف نشده است."
                sync.save(update_fields=("status", "last_error", "updated_at"))
            return sync
        if sync.payload_hash == digest and sync.status in (
            CrmContactSync.Status.PENDING,
            CrmContactSync.Status.SYNCED,
        ):
            return sync
        sync.phone_e164 = payload["phone_number"]
        sync.payload_hash = digest
        sync.status = CrmContactSync.Status.PENDING
        sync.last_error = ""
        sync.next_retry_at = timezone.now()
        sync.save()
        return sync

    @classmethod
    def sync(cls, sync):
        if not settings.CRM_ENABLED or not settings.CRM_API_KEY:
            sync.status = CrmContactSync.Status.FAILED
            sync.last_error = "CRM فعال نیست یا کلید API تنظیم نشده است."
            sync.save(update_fields=("status", "last_error", "updated_at"))
            return sync
        payload = cls.build_payload(sync.user)
        digest = cls.payload_hash(payload)
        if sync.remote_ulid:
            if sync.payload_hash != digest:
                sync.status = CrmContactSync.Status.NEEDS_REVIEW
                sync.last_error = "اطلاعات مخاطب تغییر کرده و نیازمند بررسی است."
                sync.save(update_fields=("status", "last_error", "updated_at"))
            return sync
        sync.attempts += 1
        req = request.Request(
            settings.CRM_BASE_URL.rstrip("/") + "/ci-biz/api/v1/people/create",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": settings.CRM_API_KEY, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=settings.CRM_TIMEOUT_SECONDS) as response:
                response_code = response.getcode()
                body = json.loads(response.read().decode("utf-8"))
            api_code = body.get("status", response_code)
            ulid = (body.get("data") or {}).get("ulid", "")
            sync.last_response_code = str(api_code)
            if response_code == 200 and str(api_code) in ("200", "1000") and ulid:
                sync.remote_ulid = str(ulid)
                sync.payload_hash = digest
                sync.phone_e164 = payload["phone_number"]
                sync.status = CrmContactSync.Status.SYNCED
                sync.last_error = ""
                sync.synced_at = timezone.now()
                sync.next_retry_at = None
            elif str(api_code) == "2002":
                sync.status = CrmContactSync.Status.NEEDS_REVIEW
                sync.last_error = "CRM اطلاعات مخاطب را نامعتبر تشخیص داد (2002)."
                sync.next_retry_at = None
            else:
                cls._mark_retry(sync, f"CRM request failed ({api_code}).")
        except error.HTTPError as exc:
            sync.last_response_code = str(exc.code)
            logger.warning("CRM HTTP error user_id=%s response_code=%s", sync.user_id, exc.code)
            cls._mark_retry(sync, f"CRM HTTP error ({exc.code}).")
        except (error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            logger.warning("CRM contact sync failed user_id=%s error_type=%s", sync.user_id, type(exc).__name__)
            cls._mark_retry(sync, f"خطای ارتباط با CRM: {type(exc).__name__}")
        sync.save()
        return sync

    @staticmethod
    def _mark_retry(sync, message):
        sync.last_error = message[:500]
        sync.status = CrmContactSync.Status.FAILED
        if sync.attempts < settings.CRM_MAX_ATTEMPTS:
            delay = settings.CRM_RETRY_BASE_SECONDS * (2 ** max(sync.attempts - 1, 0))
            sync.next_retry_at = timezone.now() + timedelta(seconds=delay)
        else:
            sync.next_retry_at = None

    @classmethod
    def process_pending(cls, limit=100):
        now = timezone.now()
        ids = list(
            CrmContactSync.objects.filter(
                status__in=(CrmContactSync.Status.PENDING, CrmContactSync.Status.FAILED),
                attempts__lt=settings.CRM_MAX_ATTEMPTS,
            )
            .filter(next_retry_at__isnull=True)[:limit]
            .values_list("pk", flat=True)
        )
        due_ids = list(
            CrmContactSync.objects.filter(
                status__in=(CrmContactSync.Status.PENDING, CrmContactSync.Status.FAILED),
                attempts__lt=settings.CRM_MAX_ATTEMPTS,
                next_retry_at__lte=now,
            )[: max(limit - len(ids), 0)]
            .values_list("pk", flat=True)
        )
        for sync_id in ids + due_ids:
            with transaction.atomic():
                sync = CrmContactSync.objects.select_for_update().select_related("user").get(pk=sync_id)
                cls.sync(sync)
        return len(ids) + len(due_ids)
