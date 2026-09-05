import json
import logging
import socket
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings


logger = logging.getLogger("django.request")


def _safe_provider_value(value, limit=200):
    return str(value or "").replace("\r", " ").replace("\n", " ")[:limit]


def _is_insufficient_credit(value, status_text):
    combined = f"{value} {status_text}".lower()
    return any(marker in combined for marker in (
        "insufficient credit", "insufficient balance", "credit", "balance",
        "اعتبار", "موجودی", "شارژ",
    ))


class SMSProviderError(Exception):
    def __init__(self, message, *, provider_code=""):
        super().__init__(message)
        self.provider_code = str(provider_code)


def render_sms_template(template, **context):
    try:
        return str(template).format(**context)
    except (KeyError, IndexError, ValueError) as exc:
        raise SMSProviderError(
            "The configured SMS message template is invalid.",
            provider_code="invalid_template",
        ) from exc


class PayamitoSMSService:
    endpoint = "https://rest.payamak-panel.com/api/SendSMS/SendSMS"

    @classmethod
    def send(cls, phone, text):
        if not settings.PAYAMITO_ENABLED:
            raise SMSProviderError("Payamito is disabled.", provider_code="disabled")
        if not settings.PAYAMITO_FROM_NUMBER:
            raise SMSProviderError(
                "Payamito sender number is missing.", provider_code="missing_sender"
            )
        clean_text = str(text).strip()
        if not clean_text:
            raise SMSProviderError("SMS text cannot be empty.", provider_code="empty_text")
        payload = json.dumps({
            "username": settings.PAYAMITO_USERNAME,
            "password": settings.PAYAMITO_API_KEY,
            "text": clean_text,
            "to": phone,
            "from": str(settings.PAYAMITO_FROM_NUMBER),
            "isFlash": False,
        }).encode("utf-8")
        request = Request(
            cls.endpoint,
            data=payload,
            method="POST",
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        try:
            timeout = max(1, min(int(settings.PAYAMITO_TIMEOUT_SECONDS), 10))
            with urlopen(request, timeout=timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, socket.timeout, ValueError, OSError) as exc:
            logger.warning(
                "sms_provider_transport_failure provider=payamito error_type=%s",
                type(exc).__name__,
            )
            raise SMSProviderError("Payamito is temporarily unavailable.") from exc
        ret_status = result.get("RetStatus")
        value = str(result.get("Value", ""))
        status_text = result.get("StrRetStatus", "")
        admin_code = (
            "SMS_PROVIDER_INSUFFICIENT_CREDIT"
            if _is_insufficient_credit(value, status_text)
            else "SMS_PROVIDER_RESPONSE"
        )
        log_method = logger.info if ret_status == 1 else logger.warning
        log_method(
            "sms_provider_result provider=payamito code=%s ret_status=%s value=%s str_status=%s",
            admin_code,
            _safe_provider_value(ret_status),
            _safe_provider_value(value),
            _safe_provider_value(status_text),
        )
        if ret_status != 1:
            raise SMSProviderError(
                status_text or "Payamito rejected the message.",
                provider_code=(
                    "SMS_PROVIDER_INSUFFICIENT_CREDIT"
                    if admin_code == "SMS_PROVIDER_INSUFFICIENT_CREDIT"
                    else value or ret_status
                ),
            )
        return {"message_id": value, "status": status_text or "Ok"}


# Backward-compatible import name for integrations that imported the old class.
PayamitoPatternService = PayamitoSMSService
