# جامعهٔ تخصصی V3: قرارداد و انتشار محتاطانه

این تغییر افزایشی در `apps/chat` است. هیچ دادهٔ آزمایشی در production ایجاد نمی‌کند. migration `chat.0008` فیلدهای تازه را اضافه می‌کند، پست‌های قدیمی را با مقدار پیش‌فرض `general` نگه می‌دارد و هشتگ‌های متن موجود را استخراج می‌کند. جدول‌های پست، نظر، عضویت و اتاق حذف/بازنشانی نمی‌شوند.

## API

- فید `GET/POST /api/chat/social/feed/`: `feed=for_you|following|analysis|questions|discussed`، `market` یکی از شش مقدار قرارداد، `search` و `hashtag` دقیق. صفحه‌بندی signed keyset با `results,next,previous` و snapshot؛ cursor فقط با همان فیلتر معتبر است. پست جدید `market` اجباری دارد. پست قدیمی بدون دسته `general` می‌شود.
- پست: `GET/PATCH/DELETE /api/chat/social/posts/{id}/`؛ `POST/DELETE .../useful/`؛ `POST .../poll/vote/`؛ نظرسنجی در multipart با فیلد JSON-string `poll`. گزینه‌ها پس از انتشار تغییر نمی‌کنند. نتیجه قبل از رأی یا بسته‌شدن null است.
- نظر و گزارش: `GET/POST .../posts/{id}/comments/`، `PATCH/DELETE .../comments/{id}/`، گزارش پست/نظر و `GET/PATCH /api/chat/social/manage/reports/` فقط با `CONTENT_MANAGE`.
- تحلیلگران: `GET /api/chat/social/analysts/` و `GET/PATCH /api/chat/social/manage/analysts/`؛ فعال‌سازی/نشان/امتیاز فقط مدیر.
- اتاق: `market,topic,manager` در فهرست/جزئیات؛ `POST .../{slug}/presence/` فقط عضو؛ `POST .../{slug}/invitations/` فقط مدیر/ناظر اتاق؛ `POST .../invitations/{id}/accept/` فقط گیرنده. مدیریت فعلی `?manage=true` و مسیرهای پیام/پشتیبانی حفظ می‌شوند.
- `GET /api/chat/social/community/` فقط دادهٔ قابل‌مشاهدهٔ بیننده را نشان می‌دهد. `active_rooms_count` تعداد اتاق‌های قابل‌مشاهده با حضور معتبر در TTL است. بدون Redis، تعداد حضور و اتاق فعال null و `presence_enabled=false` است؛ شمار ساختگی صفر نمایش داده نمی‌شود. `features.community_v3` پیش‌فرض false است و فقط پس از صحت‌سنجی انتشار با `SOCIAL_COMMUNITY_V3_ENABLED=True` روشن شود.

## کنترل‌های امنیت و محیط

- همهٔ endpointها JWT می‌خواهند. فید، پروفایل، ترند، جزئیات، رأی، گزارش و رسانه از policy رؤیت موجود پیروی می‌کنند. لینک اعلان هم مجوز مشاهدهٔ پست/اتاق نیست. اعلان اجتماعی متن خصوصی را حمل نمی‌کند و `send_sms=False` است.
- رسانهٔ جدید پست در `private-social-media` ذخیره می‌شود. **قبل از انتشار پست خصوصی/فالوئر،** دسترسی مستقیم Apache/WCDN به `/media/social/posts/*` قدیمی را 403/404 و purge cache را با حساب غیرمجاز بررسی کنید. مسیر مجاز `/api/chat/social/posts/{id}/media/{kind}/` Bearer JWT و Range می‌خواهد.
- از `chat.0009` به بعد تصویر و پیوست تازهٔ اتاق در همان فضای خصوصی `private-social-media` ذخیره می‌شود. پاسخ API برای تصویر اتاق `/api/chat/rooms/{id}/image/` و برای پیوست پیام `/api/chat/messages/{id}/attachment/` است؛ هر دو Bearer JWT، بررسی دسترسی در زمان درخواست، Range و `private, no-store` دارند. فرانت باید این URLها را با JWT دریافت و blob را نمایش دهد؛ تگ `<img>` مستقیم بدون هدر Authorization کافی نیست. فایل‌های قدیمی جابه‌جا/حذف نمی‌شوند؛ برای آن‌ها مسیر قدیمی `/media/chat/*` را در صورت وجود فایل خصوصی قدیمی جداگانه audit و مسدود کنید. شمار فعلی production برای رسانهٔ اتاق خصوصی در ۱۴ نوامبر صفر گزارش شد؛ این جای audit بعدی را نمی‌گیرد.
- سقف برنامهٔ Django برای جامعه: تصویر پست ۱۰MiB، ویدئوی پست ۲۰MiB، تصویر اتاق ۵MiB و پیوست اتاق ۲۰MiB. فایل بالای ۵MiB روی disk موقت می‌رود. این سقفِ اپلیکیشن، سقف WCDN/Apache را ثابت نمی‌کند. شواهد قبلی: POST حدود ۱۸۶MB از WCDN با `402` و HTML رد شده و به Gunicorn نرسیده است. برای ۲۰MiB نیز ابتدا آپلود آزمایشی زیر سقف را از مسیر عمومی CDN راستی‌آزمایی کنید؛ timeout بیشتر مشکل 402 را رفع نمی‌کند.
- حضور به `REDIS_URL` موجود متکی است، از Redis sorted-set با TTL حدود ۹۰ ثانیه استفاده می‌کند و چند تبِ یک کاربر را یک نفر می‌شمارد. نبود/خرابی Redis پیام‌ها را متوقف نمی‌کند. API heartbeat در این حالت 503 می‌دهد و فهرست `presence_enabled=false` برمی‌گرداند.
- اعتبارسنجی فایل شامل اندازه، پسوند، MIME و امضای ابتدایی فرمت ویدئو/اعتبار تصویر است؛ جایگزین اسکن بدافزار یا بررسی کامل قابل‌پخش‌بودن ویدئو نیست. متن HTML قابل اجرا ذخیره نمی‌شود.

## توالی استقرار

1. از PostgreSQL و رسانه‌ها بکاپ قابل‌بازیابی بگیرید؛ کد را در staging نصب کنید. `manage.py check`، `makemigrations --check --dry-run` و `migrate --plan` را بررسی کنید.
2. migrationهای `chat.0008` و `chat.0009` را اجرا کنید. قبل از restart وجود و مالکیت `private-social-media` را بررسی کنید. با حساب‌های آزمایشی مجاز، پست عمومی/خصوصی، بازار و هشتگ، نظرسنجی، رأی تکراری و رقابتی روی PostgreSQL، گزارش/بررسی، دعوت خصوصی، حضور TTL، رسانهٔ اتاق و اعلان بدون SMS را تست کنید. هیچ حساب/پست آزمایشی در production نسازید.
3. سقف واقعی multipart در WCDN/Apache، نمایش رسانهٔ اتاق با JWT در فرانت، و دسترسی مستقیم به رسانهٔ قدیمی را مستقل تست کنید. تا قبل از این‌ها، flag `SOCIAL_COMMUNITY_V3_ENABLED` را false نگه دارید.
4. فقط پس از تأیید کل مسیر، flag را true کنید، سرویس را restart کنید، JSON `community` و سپس `dist3` فرانت را منتشر کنید. تست SQLite به‌تنهایی اثبات race-safe بودن PostgreSQL نیست.
