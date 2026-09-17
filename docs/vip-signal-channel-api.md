# مستندات API کانال سیگنال VIP سوکانکس

## اتصال و امنیت

- Base URL: `https://api.sokanex.com`
- ارتباط: Server-to-Server
- Header الزامی: `X-Sokanex-Signal-Key: YOUR_PRIVATE_KEY`
- فرمت رسانه: `multipart/form-data`
- متن: UTF-8

کلید واقعی از متغیر محیطی `SIGNAL_CHANNEL_INGESTION_API_KEY` در اختیار مدیر ربات قرار
می‌گیرد و نباید در فرانت، پیام تلگرام، مخزن عمومی یا log قرار گیرد.

## آدرس‌ها

کریپتو:

```http
POST https://api.sokanex.com/api/signals/channels/crypto/ingest/
```

فارکس:

```http
POST https://api.sokanex.com/api/signals/channels/forex/ingest/
```

## فیلدها

| فیلد | نوع | الزام | توضیح |
|---|---|---:|---|
| `text` | string | بله | متن/caption تا ۲۰٬۰۰۰ کاراکتر؛ HTML پاک‌سازی می‌شود. |
| `external_id` | string | توصیه اکید | شناسه پایدار تا ۱۸۰ کاراکتر؛ پیشنهاد: `chat_id:message_id`. |
| `image` | file | خیر | JPG/JPEG/PNG/WebP، حداکثر ۸MB. |
| `video` | file | خیر | MP4/MOV/WebM/MKV، سقف پیش‌فرض ۱۰۰MB. |
| `audio` | file | خیر | MP3/M4A/WAV/OGG/OGA/WebM، سقف پیش‌فرض ۵۰MB. |
| `voice` | file | خیر | alias ورودی برای `audio`، مناسب Telegram Voice؛ همزمان با `audio` ارسال نشود. |
| `published_at` | ISO-8601 | خیر | مانند `2026-09-17T12:30:00+03:30`؛ پیش‌فرض زمان سرور. |

عکس، ویدئو و صدا اختیاری هستند، اما `text` مطابق قرارداد فعلی الزامی است.

## cURL کریپتو با ویدئو و Voice

```bash
curl --fail-with-body -X POST \
  "https://api.sokanex.com/api/signals/channels/crypto/ingest/" \
  -H "X-Sokanex-Signal-Key: YOUR_PRIVATE_KEY" \
  -F "external_id=-1001234567890:846" \
  -F "text=متن کامل سیگنال کریپتو" \
  -F "published_at=2026-09-17T12:30:00+03:30" \
  -F "video=@/absolute/path/signal.mp4;type=video/mp4" \
  -F "voice=@/absolute/path/voice.oga;type=audio/ogg"
```

## cURL فارکس با عکس و Audio

```bash
curl --fail-with-body -X POST \
  "https://api.sokanex.com/api/signals/channels/forex/ingest/" \
  -H "X-Sokanex-Signal-Key: YOUR_PRIVATE_KEY" \
  -F "external_id=-1009876543210:125" \
  -F "text=متن کامل سیگنال فارکس" \
  -F "image=@/absolute/path/chart.webp;type=image/webp" \
  -F "audio=@/absolute/path/explanation.mp3;type=audio/mpeg"
```

## فقط متن با JSON

```bash
curl --fail-with-body -X POST \
  "https://api.sokanex.com/api/signals/channels/crypto/ingest/" \
  -H "X-Sokanex-Signal-Key: YOUR_PRIVATE_KEY" \
  -H "Content-Type: application/json" \
  --data '{"external_id":"-100123:999","text":"متن سیگنال"}'
```

## نمونه Python برای ربات تلگرام

```python
from contextlib import ExitStack
from pathlib import Path
import mimetypes
import requests

BASE_URL = "https://api.sokanex.com"
API_KEY = "YOUR_PRIVATE_KEY"  # در عمل از env ربات خوانده شود.


def publish_signal(channel, chat_id, message_id, text, *, image=None, video=None, voice=None):
    if channel not in {"crypto", "forex"}:
        raise ValueError("channel must be crypto or forex")

    url = f"{BASE_URL}/api/signals/channels/{channel}/ingest/"
    headers = {"X-Sokanex-Signal-Key": API_KEY}
    data = {"external_id": f"{chat_id}:{message_id}", "text": text}

    with ExitStack() as stack:
        files = {}
        for field, path_value in {"image": image, "video": video, "voice": voice}.items():
            if not path_value:
                continue
            path = Path(path_value)
            handle = stack.enter_context(path.open("rb"))
            mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            files[field] = (path.name, handle, mime)
        response = requests.post(
            url, headers=headers, data=data, files=files or None, timeout=(10, 120)
        )

    if response.status_code in {429, 500, 502, 503, 504}:
        raise RuntimeError(f"temporary failure: {response.status_code}")
    response.raise_for_status()
    return response.json()
```

Telegram Voice معمولاً `.oga` با MIME برابر `audio/ogg` است. ربات باید فایل را از Telegram
دانلود و بایت‌های فایل را با multipart ارسال کند؛ `file_id` یا URL تلگرام به‌تنهایی پذیرفته نیست.

## پاسخ

- `201 Created`: پست جدید ساخته شد.
- `200 OK`: `external_id` قبلاً ثبت شده و همان رکورد برگردانده شد.

```json
{
  "id": 42,
  "kind": "VIP_CHANNEL_POST",
  "channel": "CRYPTO",
  "channel_label": "کانال وی آی پی سوکانکس (کریپتو)",
  "text": "متن کامل سیگنال",
  "excerpt": "۳۰ کلمه اول متن…",
  "image": "https://api.sokanex.com/media/signals/vip/crypto/example.webp",
  "video": "https://api.sokanex.com/media/signals/vip/crypto/video/example.mp4",
  "audio": "https://api.sokanex.com/media/signals/vip/crypto/audio/example.oga",
  "source": "TELEGRAM_API",
  "published_at": "2026-09-17T12:30:00+03:30",
  "created_at": "2026-09-17T12:30:03+03:30"
}
```

رسانه ارسال‌نشده `null` است. `voice` فقط alias ورودی است و خروجی canonical آن `audio` است.

## خطا و Retry

- `400`: داده، MIME، پسوند یا حجم نامعتبر؛ پس از اصلاح payload دوباره ارسال شود.
- `401`: کلید مفقود یا اشتباه است.
- `413`: محدودیت آپلود CDN/Nginx کمتر از فایل است.
- `429`: با exponential backoff و همان `external_id` retry شود.
- `503`: ingestion روی Backend پیکربندی نشده است.
- `5xx`: retry محدود با همان `external_id`.

در هر retry همان `external_id` استفاده شود تا رکورد تکراری ساخته نشود.

## API خواندن مخصوص فرانت

```http
GET https://api.sokanex.com/api/signals/?channel=crypto
GET https://api.sokanex.com/api/signals/?channel=forex
Authorization: Bearer USER_ACCESS_TOKEN
```

این endpointها JWT کاربر می‌خواهند؛ کلید ربات هرگز در فرانت استفاده نمی‌شود.
