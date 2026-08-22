import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings


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
            with urlopen(request, timeout=min(settings.PAYAMITO_TIMEOUT_SECONDS, 15)) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
            raise SMSProviderError("Payamito is temporarily unavailable.") from exc
        ret_status = result.get("RetStatus")
        value = str(result.get("Value", ""))
        if ret_status != 1:
            raise SMSProviderError(
                result.get("StrRetStatus") or "Payamito rejected the message.",
                provider_code=value or ret_status,
            )
        return {"message_id": value, "status": result.get("StrRetStatus", "Ok")}


# Backward-compatible import name for integrations that imported the old class.
PayamitoPatternService = PayamitoSMSService
