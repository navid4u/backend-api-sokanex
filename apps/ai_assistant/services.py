import base64
import json
import logging
import time
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.utils import timezone

from .crypto import decrypt_token
from .exceptions import AssistantError
from .models import AISettings, AIUsageLog


logger = logging.getLogger(__name__)
DISCLAIMER = "این پاسخ صرفاً آموزشی است و توصیه قطعی مالی یا تضمین سود محسوب نمی‌شود."


class AssistantService:
    @classmethod
    def _ready(cls, mode):
        config = AISettings.load()
        if not config.enabled:
            raise AssistantError("دستیار هوشمند هنوز برای استفاده فعال نشده است.", "ASSISTANT_NOT_CONFIGURED", 503)
        limit = config.daily_user_limit if mode == AIUsageLog.Mode.FINANCIAL else config.image_daily_user_limit
        if limit == 0:
            raise AssistantError("این قابلیت هنوز برای استفاده فعال نشده است.", "ASSISTANT_NOT_CONFIGURED", 503)
        if not config.api_token_encrypted or not config.model:
            raise AssistantError("توکن یا مدل دستیار توسط مدیر تنظیم نشده است.", "ASSISTANT_NOT_CONFIGURED", 503)
        try:
            decrypt_token(config.api_token_encrypted)
        except (ImproperlyConfigured, ValueError, TypeError):
            raise AssistantError(
                "تنظیمات امن دستیار نیاز به ثبت مجدد توکن دارد.",
                "ASSISTANT_NOT_CONFIGURED",
                503,
            ) from None
        return config, limit

    @classmethod
    def _used_today(cls, user, mode):
        start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
        return AIUsageLog.objects.filter(user=user, mode=mode, status=AIUsageLog.Status.SUCCESS, created_at__gte=start).count()

    @classmethod
    def run(cls, user, mode, messages):
        config, limit = cls._ready(mode)
        used = cls._used_today(user, mode)
        if used >= limit:
            raise AssistantError("سهمیه روزانه شما تمام شده است.", "DAILY_LIMIT_REACHED", 429)
        started = time.monotonic()
        provider_status = None
        try:
            payload, provider_status = cls._request(config, messages)
            choice = (payload.get("choices") or [{}])[0]
            answer = ((choice.get("message") or {}).get("content") or "").strip()
            if not answer:
                raise AssistantError("پاسخ معتبری از سرویس دریافت نشد.", "INCOMPLETE_PROVIDER_RESPONSE", 502)
            usage = payload.get("usage") or {}
            input_tokens = int(usage.get("prompt_tokens") or 0)
            output_tokens = int(usage.get("completion_tokens") or 0)
            AIUsageLog.objects.create(user=user, mode=mode, status="success", input_tokens=input_tokens, output_tokens=output_tokens, latency_ms=int((time.monotonic()-started)*1000), provider_status=provider_status)
            return answer, {"remaining_today": max(0, limit-used-1), "input_tokens": input_tokens, "output_tokens": output_tokens}
        except AssistantError:
            AIUsageLog.objects.create(user=user, mode=mode, status="error", latency_ms=int((time.monotonic()-started)*1000), provider_status=provider_status)
            raise

    @staticmethod
    def _request(config, messages):
        body = json.dumps({"model": config.model, "messages": messages, "temperature": config.temperature, "max_tokens": config.max_tokens}).encode()
        request = Request(f"{config.base_url.rstrip('/')}/chat/completions", data=body, headers={"Authorization": f"Bearer {decrypt_token(config.api_token_encrypted)}", "Content-Type": "application/json", "Accept": "application/json"}, method="POST")
        for attempt in range(2):
            try:
                with urlopen(request, timeout=config.request_timeout) as response:
                    return json.loads(response.read().decode()), response.status
            except HTTPError as exc:
                if exc.code in (429, 502, 503) and attempt == 0:
                    time.sleep(0.25)
                    continue
                if exc.code in (401, 403):
                    code, response_status = "PROVIDER_AUTH_ERROR", 502
                elif exc.code == 429:
                    code, response_status = "PROVIDER_RATE_LIMIT", 429
                elif exc.code in (502, 503, 504):
                    code, response_status = "PROVIDER_UNAVAILABLE", 503
                else:
                    code, response_status = "PROVIDER_ERROR", 502
                raise AssistantError("ارتباط با سرویس هوشمند ناموفق بود.", code, response_status) from exc
            except (URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
                raise AssistantError("سرویس هوشمند در زمان مقرر پاسخ نداد.", "PROVIDER_TIMEOUT", 503) from exc

    @classmethod
    def financial(cls, user, messages):
        config = AISettings.load()
        server_messages = [{"role": "system", "content": config.financial_system_prompt}] + messages
        answer, usage = cls.run(user, AIUsageLog.Mode.FINANCIAL, server_messages)
        if DISCLAIMER not in answer:
            answer = f"{answer}\n\n{DISCLAIMER}"
        return answer, usage

    @classmethod
    def technical(cls, user, image_bytes, mime):
        config = AISettings.load()
        data_url = f"data:{mime};base64,{base64.b64encode(image_bytes).decode()}"
        prompt = config.technical_system_prompt + "\nخروجی شامل روند، حمایت‌ها، مقاومت‌ها، سناریوی صعودی و نزولی، محدوده احتمالی ورود، حد ابطال و هشدار عدم قطعیت باشد."
        messages = [{"role": "system", "content": prompt}, {"role": "user", "content": [{"type": "text", "text": "این نمودار را تحلیل کن."}, {"type": "image_url", "image_url": {"url": data_url}}]}]
        try:
            answer, usage = cls.run(user, AIUsageLog.Mode.TECHNICAL, messages)
        except AssistantError as exc:
            if exc.machine_code in ("INCOMPLETE_PROVIDER_RESPONSE", "PROVIDER_ERROR"):
                exc.machine_code = "VISION_NOT_SUPPORTED"
                exc.status_code = 422
            raise
        if DISCLAIMER not in answer:
            answer = f"{answer}\n\n{DISCLAIMER}"
        return answer, usage
