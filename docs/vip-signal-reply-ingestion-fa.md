# قرارداد قطعی Reply برای ربات کانال‌های VIP

Base URL: `https://api.sokanex.com`

مسیر کریپتو: `POST /api/signals/channels/crypto/ingest/`

مسیر فارکس: `POST /api/signals/channels/forex/ingest/`

احراز هویت مانند قبل با header خصوصی `X-Sokanex-Signal-Key` و مقدار `SIGNAL_CHANNEL_INGESTION_API_KEY` در تنظیمات بک‌اند است. کلید فقط روی سرور ربات نگه داشته شود و در فرانت/URL قرار نگیرد. پاسخ `201` برای پست تازه و `200` برای retry همان `external_id` است.

## فیلدهای Reply

- `external_id`: شناسه پایدار خود پیام، مانند `telegram:-1001234567890:456`؛ برای Reply الزامی است.
- `reply_to_external_id`: همان قالب برای پیام مرجع. بازار مرجع باید با endpoint یکی باشد.
- `reply_snapshot`: اختیاری؛ object با فقط `text` (متن ساده، حداکثر ۵۰۰ کاراکتر) و `media_type` (`image`، `video`، `audio` یا null). برای parent قدیمی یا ناموجود، ربات باید متن/نوع رسانه را از `reply_json` موجود در D1 استخراج کند و این snapshot را ارسال کند. خود `reply_json` یا `telegram_message_json` به API ارسال نمی‌شود.
- `text`: متن خود Reply، مانند قبل الزامی است؛ `image`، `video`، `audio` یا `voice` همچنان اختیاری‌اند.

نمونه JSON بدون رسانه:

```bash
curl -X POST 'https://api.sokanex.com/api/signals/channels/crypto/ingest/' \
  -H 'X-Sokanex-Signal-Key: YOUR_PRIVATE_KEY' \
  -H 'Content-Type: application/json' \
  --data '{"external_id":"telegram:-1001234567890:456","reply_to_external_id":"telegram:-1001234567890:450","reply_snapshot":{"text":"متن پیام مرجع","media_type":"image"},"text":"متن پاسخ"}'
```

برای فایل، `multipart/form-data` بفرستید و `reply_snapshot` را یک رشته JSON معتبر قرار دهید:

```bash
curl -X POST 'https://api.sokanex.com/api/signals/channels/forex/ingest/' \
  -H 'X-Sokanex-Signal-Key: YOUR_PRIVATE_KEY' \
  -F 'external_id=telegram:-1009876543210:121' \
  -F 'reply_to_external_id=telegram:-1009876543210:119' \
  -F 'reply_snapshot={"text":"متن مرجع","media_type":"video"}' \
  -F 'text=پاسخ فارکس' \
  -F 'image=@/absolute/path/photo.jpg'
```

برای پیام معمولی فقط `external_id`، `text` و رسانه‌های قبلی را بفرستید. کلیدها و endpointهای قبلی عوض نشده‌اند.

## رفتار حل مرجع

اگر parent قبلاً در همان بازار ذخیره شده باشد، `reply_preview.available=true`، `reply_preview.id` شناسه داخلی parent و `reply_preview.text` متن کامل مرجع است. اگر parent هنوز نرسیده باشد، Reply فوراً با `is_active=true` و پاسخ `201` ذخیره می‌شود و در GET هم دیده می‌شود؛ `available=false`، `id=null`، `media_type=null` و متن snapshot (در صورت ارسال) برمی‌گردد. با رسیدن parent، رابطه خودکار وصل می‌شود. اگر parent از قبل حذف شده یا بعداً حذف/غیرفعال شود، لینک داخلی null می‌شود ولی متن snapshot ذخیره‌شده باقی می‌ماند. بک‌اند هیچ وضعیت `WAITING_REPLY_CONTRACT` ندارد؛ این وضعیت باید از صف Worker ربات حذف شود.

ارسال مجدد همان `external_id` رابطه موجود را حفظ می‌کند. اگر پست پیش از فعال‌سازی قرارداد به‌صورت مستقل ذخیره شده باشد، retry با `reply_to_external_id` می‌تواند یک بار رابطه را به همان رکورد اضافه کند. retry با parent متفاوت `409` می‌دهد. self-reply، چرخه و ارجاع به پیام شناخته‌شده در بازار دیگر `400` می‌دهد. `reply_snapshot` بدون `reply_to_external_id` هم `400` است.

نمونه بخش تازه پاسخ ingest/GET:

```json
{
  "id": 42,
  "channel": "CRYPTO",
  "text": "متن پاسخ",
  "reply_to_external_id": "telegram:-1001234567890:450",
  "reply_preview": {
    "id": 39,
    "text": "متن پیام مرجع",
    "media_type": "image",
    "available": true
  }
}
```

این فیلدها در پاسخ `GET /api/signals/?channel=CRYPTO|FOREX` و `GET /api/signals/{id}/` نیز هستند. خواندن آن‌ها فقط با JWT کاربر دارای دسترسی GOLD انجام می‌شود؛ کلید ingest برای GET کاربر استفاده نمی‌شود.
