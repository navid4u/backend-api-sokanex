# استقرار تغییرات پاسخ پشتیبانی، GOLD و رسانهٔ اجتماعی

این تغییر فقط در کد محلی/مخزن آماده می‌شود؛ اجرای production نیازمند بکاپ، migration و آزمون staging است. هیچ SMS آزمایشی به کاربر واقعی نفرستید.

## ترتیب استقرار

1. از PostgreSQL و `MEDIA_ROOT` بکاپ بازیابی‌پذیر بگیرید. قبل از migration، سرویس‌ها و تنظیمات Apache/WCDN را ثبت کنید.
2. کد را fast-forward کنید. `manage.py check`، `makemigrations --check --dry-run`، `migrate --plan` و سپس `migrate --noinput` را اجرا کنید. migrationهای `accounts.0031` و `chat.0007` دادهٔ تاریخی را حذف نمی‌کنند.
   پیش از فعال‌کردن آپلود پست، روی سرور `install -d -o tradingapp -g tradingapp -m 0700 /srv/trading-platform/private-social-media` را اجرا کنید و مالکیت/مسیر را بررسی کنید.
3. در staging، با حساب پشتیبانی و گیرندهٔ آزمایشیِ مجاز پاسخ دهید: یک `Notification` با `source_key=SUPPORT_REPLY:<message_id>` و حداکثر یک `NotificationSMSDelivery` در وضعیت PENDING باید ساخته شود. پاسخ مشتری هیچ‌کدام را ایجاد نمی‌کند. provider در درخواست HTTP صدا زده نمی‌شود.
4. پس از تأیید staging، فایل‌های `deployment/systemd/sokanex-support-reply-sms.{service,timer}` را نصب و timer را فعال کنید. این timer فقط notificationهای با `source_key` آغازشونده با `SUPPORT_REPLY:` را از صف موجود ارسال می‌کند و مستقل از timer کمپین انبوه است. `SENT` فقط پذیرش provider است، نه الزاماً تحویل گوشی.
5. برای GOLD، فرانت باید `revision` برگشتی از GET فهرست را هنگام PATCH تأیید در `expected_revision` بفرستد. برای درخواست اصلاح‌شده (`revision > 1`) نبودن یا قدیمی‌بودن این مقدار 409 می‌دهد؛ مدیر باید فهرست را تازه کند. درخواست‌های قدیمی با revision=1 مانند قبل تأیید می‌شوند.

## رسانهٔ خصوصی

- آپلودهای جدید پست در مسیر پیش‌فرض `../private-social-media` نسبت به `BASE_DIR` ذخیره می‌شوند. این مسیر باید خارج از وب‌روت و `/media/`، قابل‌نوشتن برای `tradingapp` و غیرقابل‌خواندن برای وب‌سرور مستقیم باشد.
- `image` و `video` پاسخ فید اکنون `/api/chat/social/posts/<id>/media/image|video/` را برمی‌گردانند. GET این مسیر به JWT و مجوز دیدن پست نیاز دارد، `Range` را با 206 پشتیبانی می‌کند، و `Cache-Control: private, no-store` می‌دهد. پخش‌کنندهٔ فرانت باید Range را با `Authorization` ارسال کند؛ تگ سادهٔ `<video src>` معمولاً هدر Bearer نمی‌فرستد.
- فایل‌های قدیمی زیر `MEDIA_ROOT/social/posts/` از طریق endpoint مجاز به‌صورت fallback خوانده می‌شوند، اما **تا وقتی Apache و WCDN دسترسی مستقیم `/media/social/posts/*` را رد و cache قدیمی را purge نکرده‌اند، حریم خصوصی آن‌ها کامل نیست**. پس از بستن مسیر مستقیم، با یک حساب غیرمجاز، GET URL قدیمی را 403/404 و GET API رسانهٔ FOLLOWERS/PRIVATE را 404 آزمایش کنید. قبل از آن، انتشار قابلیت استوری خصوصی را انجام ندهید.
- سقف اعتبارسنجی Django برای تصویر ۱۰MB و ویدئو ۲۰۰MB است. سقف request body و timeout در WCDN و Apache باید جدا بررسی شوند. 402/HTML در WCDN پیش از رسیدن به Django با کد بک‌اند حل نمی‌شود. تست واقعی multipart کوچک و یک Range فقط در staging انجام شود.

## کلید دستیار

کلید افشاشده باید توسط مالک حساب در ارائه‌دهنده revoke شود. کلید تازه را فقط در پنل مدیریت دستیار از طریق PATCH موجودِ write-only `api_token` ثبت کنید؛ مقدار را در shell history، log، فایل فرانت یا این گزارش وارد نکنید. GET فقط `token_configured` و وضعیت پیکربندی را برمی‌گرداند. تست ارتباط با provider فقط با حساب و محیط مجاز انجام شود.
