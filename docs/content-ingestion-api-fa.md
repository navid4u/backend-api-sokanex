# API انتشار محتوای ربات سوکانکس

آدرس پایه production: `https://api.sokanex.com`

تمام درخواست‌های انتشار باید header زیر را داشته باشند:

```http
X-Sokanex-Ingest-Key: YOUR_SECRET_KEY
```

کلید فقط روی سرور ربات نگهداری شود و نباید داخل React، Telegram message، URL یا Git قرار بگیرد.

## تحلیل داخلی

`POST /api/channels/internal-analysis/ingest/`

نوع درخواست می‌تواند `application/json` (بدون فایل) یا `multipart/form-data` باشد.

فیلدهای اجباری: `scope`، `title` و `body`.

مقادیر scope: `DOLLAR`، `GOLD`، `STOCK`، `FOREX`، `HOUSING`.

فیلدهای اختیاری: `external_id`، `image`، `video` و `audio`.

## سیگنال ساده

`POST /api/signals/ingest/`

فیلدهای اجباری: `title` و `description`.

فیلدهای اختیاری: `external_id` و `image`.

محتوا بلافاصله با وضعیت approved منتشر و برای سطوح ۱ تا ۵ قابل مشاهده می‌شود.

## Idempotency

ربات باید برای هر پیام تلگرام یک `external_id` ثابت و یکتا، مانند `telegram:channel-id:message-id` ارسال کند. اولین درخواست HTTP 201 و retry همان پیام HTTP 200 می‌گیرد و رکورد تکراری ایجاد نمی‌شود.

## مشاهده فقط ورودی‌های ربات

- `GET /api/channels/internal-analysis/?source=TELEGRAM_API`
- `GET /api/signals/?source=TELEGRAM_API`

این endpointهای مشاهده مانند قبل از JWT کاربر اپ استفاده می‌کنند؛ کلید ingestion فقط برای دو endpoint POST است.
