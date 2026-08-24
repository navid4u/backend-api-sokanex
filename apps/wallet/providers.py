import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings


class PaymentProviderError(Exception):
    pass


def _post(url, payload, headers=None):
    last_error = None
    attempts = max(1, min(settings.PAYMENT_PROVIDER_RETRY_LIMIT + 1, 3))
    for _ in range(attempts):
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        try:
            with urlopen(
                request, timeout=min(settings.PAYMENT_PROVIDER_TIMEOUT_SECONDS, 30)
            ) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
            last_error = exc
    raise PaymentProviderError("Payment provider is temporarily unavailable.") from last_error


class ZarinpalAdapter:
    request_url = "https://api.zarinpal.com/pg/v4/payment/request.json"
    verify_url = "https://api.zarinpal.com/pg/v4/payment/verify.json"

    @classmethod
    def create(cls, payment, callback_url):
        result = _post(cls.request_url, {
            "merchant_id": settings.ZARINPAL_MERCHANT_ID, "amount": payment.amount_irt,
            "currency": "IRT", "description": f"Sokanex {payment.purpose}",
            "callback_url": callback_url,
            "metadata": {"mobile": payment.user.phone or "", "order_id": str(payment.id)},
        })
        data = result.get("data") or {}
        if data.get("code") != 100 or not data.get("authority"):
            raise PaymentProviderError("Zarinpal rejected the request.")
        return data["authority"], f"https://www.zarinpal.com/pg/StartPay/{data['authority']}"

    @classmethod
    def verify(cls, payment, authority):
        result = _post(cls.verify_url, {"merchant_id": settings.ZARINPAL_MERCHANT_ID, "amount": payment.amount_irt, "authority": authority})
        data = result.get("data") or {}
        if data.get("code") not in (100, 101):
            raise PaymentProviderError("Zarinpal verification failed.")
        if data.get("amount") is not None and int(data["amount"]) != payment.amount_irt:
            raise PaymentProviderError("Payment amount mismatch.")
        return str(data.get("ref_id", ""))


class IDPayAdapter:
    request_url = "https://api.idpay.ir/v1.1/payment"
    verify_url = "https://api.idpay.ir/v1.1/payment/verify"

    @classmethod
    def headers(cls):
        headers = {"X-API-KEY": settings.IDPAY_API_KEY}
        if settings.IDPAY_SANDBOX:
            headers["X-SANDBOX"] = "1"
        return headers

    @classmethod
    def create(cls, payment, callback_url):
        result = _post(cls.request_url, {
            "order_id": str(payment.id), "amount": payment.amount_irt * 10,
            "name": payment.user.get_full_name() or payment.user.username,
            "phone": payment.user.phone or "", "desc": f"Sokanex {payment.purpose}", "callback": callback_url,
        }, cls.headers())
        if not result.get("id") or not result.get("link"):
            raise PaymentProviderError(result.get("error_message", "IDPay rejected the request."))
        return result["id"], result["link"]

    @classmethod
    def verify(cls, payment, authority):
        result = _post(cls.verify_url, {"id": authority, "order_id": str(payment.id)}, cls.headers())
        if int(result.get("status", 0)) not in (100, 101, 200):
            raise PaymentProviderError(result.get("error_message", "IDPay verification failed."))
        if int(result.get("amount", 0)) != payment.amount_irt * 10:
            raise PaymentProviderError("Payment amount mismatch.")
        return str(result.get("track_id", ""))


ADAPTERS = {"ZARINPAL": ZarinpalAdapter, "IDPAY": IDPayAdapter}
