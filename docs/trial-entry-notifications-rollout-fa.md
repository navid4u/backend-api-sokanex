# استقرار مرحله‌ای ورود Trial و اعلان‌ها

این تغییر فقط کد محلی است تا زمانی که commit/push و deploy انجام شود. `TRIAL_EXISTING_LOGIN_ENABLED` پیش‌فرض `False` دارد. روشن‌کردن آن برای اولین ورود حساب قدیمیِ بدون Trial جاری، دسترسی‌های V2 تأییدشدهٔ قبلی و نشان Elite را با audit حذف می‌کند؛ این عمل با خاموش‌کردن flag برنمی‌گردد. پیش از آن backup دیتابیس و snapshot معمول را تأیید کنید.

## ترتیب امن

1. نسخهٔ حاوی migration `notifications.0007_notification_event_scope` را deploy کنید. `python manage.py check`، `python manage.py makemigrations --check --dry-run` و `python manage.py migrate --noinput` را اجرا کنید. پیش از migration، سرویس ingest سیگنال و worker پیامک را با کد جدید restart نکنید.
2. API و timer پیامک را restart کنید. `systemctl is-active trading-platform.service sokanex-sms-automation.timer`، `/api/health/` و لاگ‌های سرویس را بررسی کنید. timer اعلان push (`sokanex-notification-push.timer`) فقط در صورت پیکربندی VAPID باید فعال باشد؛ اعلان داخل اپ بدون آن کار می‌کند.
3. با superadmin، `POST /api/accounts/admin/market-access/trial-campaigns/preview/` را با بدنهٔ `{}` و `GET /api/accounts/admin/market-access/trial-campaigns/eligible-users/?page=1&page_size=20` را مقایسه کنید. `candidate_digest` فقط کنترل هم‌زمانی است، نام مخاطب نیست. فیلتر `registered_from` را خالی بگذارید مگر واقعاً cohort تاریخی می‌خواهید.
4. اگر مقادیر و backup درست‌اند، `TRIAL_EXISTING_LOGIN_ENABLED=True` را به environment هر process API اضافه و سرویس را restart کنید. این flag در worker SMS لازم نیست. `MARKET_ACCESS_V2_ENABLED=True` و تنظیم مدیریتی `auto_start_new_users=true` نیز شرط‌اند.
5. یک حساب قدیمیِ **فاقد TrialGrant غیر-invalidated** را تست کنید: ورود عادی یا `POST /api/accounts/market-access/trial/ensure/` باید فقط بار اول `started=true` دهد. پروفایل/داشبورد باید `market_access_v2.trial_status=ACTIVE`، `trial_days_remaining=7` و سه بازار مؤثر را نشان دهد. تکرار، تاریخ پایان را تغییر ندهد. حسابی که Trial معتبر قبلی دارد نباید دوباره شروع شود.
6. برای گذشت زمان مصنوعی از دادهٔ production استفاده نکنید. انقضا در تست خودکار پوشش دارد؛ در production worker `process_sms_automation` هر بار audit انقضا می‌گیرد و resolver دسترسی را از زمان سرور محاسبه می‌کند. درخواست GOLD پس از انقضا با endpoint V2 است.
7. یک SMS غیرامنیتی و یک ingest VIP آزمایشی مجاز را جداگانه بررسی کنید: `SMSAutomationDelivery.status=SENT`، اعلان شخصی در `/api/notifications/`، و اعلان سیگنال فقط برای بازار مجاز و فقط یک بار برای retry. متن OTP عمداً هرگز در اعلان کپی نمی‌شود.

## توقف اضطراری

`TRIAL_EXISTING_LOGIN_ENABLED=False` را در API قرار دهید و سرویس را restart کنید؛ این فقط شروع‌های **بعدی** را متوقف می‌کند. برای برگرداندن grantهای از قبل لغوشده باید با audit و backup، بازگردانی موردیِ تأییدشده انجام شود؛ rollback کد به‌تنهایی آن‌ها را بازنمی‌گرداند. از restore کل snapshot بدون بررسی پیامک‌ها، ثبت‌نام‌ها و تغییرات بعد از snapshot خودداری کنید.
