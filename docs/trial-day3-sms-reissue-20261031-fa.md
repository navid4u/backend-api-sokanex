# ارسال متن اصلاح‌شدهٔ روز سوم فقط به دریافت‌نکرده‌ها

این عملیات فقط برای کمپین ثابت `all_normal_users_2026_10_29` است. منبع مخاطبان، پیامک‌های روز سوم با وضعیت `SKIPPED` و علت `DAY3_TEXT_CHANGE_CANCELLED` است؛ پیام‌های `SENT` قبلی دوباره ارسال نمی‌شوند. متن از تنظیم فعلی روز سوم در «مسیر هفت‌روزه» خوانده و هنگام ساخت ردیف‌های تازه ثابت می‌شود. تاریخ Trial، سایر روزها و سابقهٔ SMS اصلی تغییر نمی‌کنند. فرمان dry-run هیچ پیامکی صف یا ارسال نمی‌کند.

## قبل از صف‌گذاری

```bash
systemctl disable --now sokanex-sms-automation.timer
systemctl stop sokanex-sms-automation.service
systemctl is-enabled sokanex-sms-automation.timer
systemctl is-active sokanex-sms-automation.timer sokanex-sms-automation.service
```

خروجی باید `disabled` و دو بار `inactive` باشد. سپس بکاپ بگیرید و کد جدید را با `git merge --ff-only` دریافت کنید. هیچ migration جدیدی وجود ندارد. `manage.py check` و `migrate --check` را اجرا کنید. تا تأیید متن و صف، تایمر خاموش بماند.

## پیش‌نمایش بدون ارسال

```bash
cd /srv/trading-platform/backend
MARKET_ACCESS_V2_ENABLED=True /srv/trading-platform/venv/bin/python manage.py reissue_trial_day_three_sms_20261029 --actor superadmin
```

`day_three_text` را بصری تأیید کنید. انتظار فعلی `source_cancelled_count=4516` و `original_day_three_sent_preserved=399` است، ولی فقط شمارش همان لحظهٔ سرور معتبر است. `already_applied` باید `false` باشد. `new_pending_count` تعداد واقعی پیام‌های قابل ارسال است و ممکن است به‌دلیل غیرفعال‌شدن حساب، تغییر شماره یا پایان Trial کمتر از ۴۵۱۶ باشد. `other_pending_messages` را نیز بررسی کنید؛ روشن‌کردن کارگر همهٔ پیام‌های در صف را پردازش خواهد کرد.

## اعمال با مقادیر همان پیش‌نمایش

```bash
MARKET_ACCESS_V2_ENABLED=True /srv/trading-platform/venv/bin/python manage.py reissue_trial_day_three_sms_20261029 --actor superadmin --apply --confirm-send-to-cancelled-only --confirm-worker-stopped --expected-count N --expected-candidate-digest AUDIENCE_SHA --expected-template-digest TEXT_SHA
```

`N`، `AUDIENCE_SHA` و `TEXT_SHA` را دقیقاً از خروجی تازهٔ dry-run بردارید. اگر مخاطبان یا متن بین پیش‌نمایش و اعمال تغییر کنند، هیچ ردیف تازه‌ای ساخته نمی‌شود. اجرای تکراری همان عملیات پیام تکراری نمی‌سازد. خروجی `new_pending` و `new_skipped` را بررسی کنید؛ اگر اختلاف غیرمنتظره دارد تایمر را روشن نکنید. پیام `SENT` به معنی پذیرش پیامیتو است، نه تحویل قطعی به گوشی. `SENDING` پس از توقف غیرمنتظره باید دستی بررسی شود و خودکار retry نمی‌شود.

پس از تأیید خروجی و رضایت مالک از متن/تعداد، تایمر را فعال کنید:

```bash
systemctl enable --now sokanex-sms-automation.timer
systemctl list-timers --all --no-pager | grep -F sokanex-sms-automation
```

کارگر فعلی حداکثر ۱۰۰ پیام در هر اجرا پردازش می‌کند. ردیف‌های لغوشدهٔ اصلی در گزارش با علت خود باقی می‌مانند و ردیف‌های جدید با event `JOURNEY_DAY3_REISSUE` قابل شمارش‌اند.
