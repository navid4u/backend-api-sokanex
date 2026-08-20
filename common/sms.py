import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings


class SMSProviderError(Exception):
    def __init__(self, message, *, provider_code=""):
        super().__init__(message)
        self.provider_code = str(provider_code)


class PayamitoPatternService:
    endpoint = "https://rest.payamak-panel.com/api/SendSMS/BaseServiceNumber"

    @classmethod
    def send(cls, phone, body_id, variables):
        if not settings.PAYAMITO_ENABLED:
            raise SMSProviderError("Payamito is disabled.", provider_code="disabled")
        if not body_id:
            raise SMSProviderError("Payamito pattern body ID is missing.", provider_code="missing_body_id")
        clean_variables = [str(value).replace(";", " ").strip() for value in variables]
        if any("http://" in value.lower() or "https://" in value.lower() for value in clean_variables):
            raise SMSProviderError("Links are not allowed in service-pattern variables.", provider_code="-10")
        payload = json.dumps({
            "username": settings.PAYAMITO_USERNAME,
            "password": settings.PAYAMITO_API_KEY,
            "text": ";".join(clean_variables),
            "to": phone,
            "bodyId": int(body_id),
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
