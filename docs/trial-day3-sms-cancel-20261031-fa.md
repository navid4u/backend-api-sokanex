# توقف صف پیامک روز سوم کمپین ۲۹ اکتبر

این فرمان فقط پیامک‌های `PENDING` روز سوم کمپین `all_normal_users_2026_10_29` را لغو می‌کند. پیام‌های `SENT`، سایر روزها، تاریخ Trial، OTP و اعلان‌های داخل اپ تغییر نمی‌کنند. تاریخچهٔ پیام‌های لغوشده حذف نمی‌شود و علت `DAY3_TEXT_CHANGE_CANCELLED` در گزارش می‌ماند. این فرمان خودش هیچ پیامکی ارسال نمی‌کند.

ابتدا تایمر را خاموش و سرویس در حال اجرا را متوقف کنید. پیامک پذیرفته‌شده توسط ارائه‌دهنده برگشت‌پذیر نیست و `SENDING` باید پیش از لغو بررسی شود:

```bash
systemctl disable --now sokanex-sms-automation.timer
systemctl stop sokanex-sms-automation.service
systemctl is-enabled sokanex-sms-automation.timer
systemctl is-active sokanex-sms-automation.timer sokanex-sms-automation.service
```

خروجی باید `disabled` و دو بار `inactive` باشد. سپس از دیتابیس بکاپ بگیرید، نسخهٔ جدید را دریافت کنید و پیش‌نمایش بدون تغییر بگیرید:

```bash
cd /srv/trading-platform/backend
systemctl start trading-platform-backup.service
systemctl show trading-platform-backup.service -p Result -p ExecMainStatus --no-pager
git fetch origin backend-with-frontedits
git merge --ff-only origin/backend-with-frontedits
/srv/trading-platform/venv/bin/python manage.py check
/srv/trading-platform/venv/bin/python manage.py migrate --check
MARKET_ACCESS_V2_ENABLED=True /srv/trading-platform/venv/bin/python manage.py cancel_trial_day_three_sms_20261029 --actor superadmin
```

پیش‌نمایش باید `day=3`، `sending_needs_review=0` و تعداد مورد انتظار در `pending_to_cancel` داشته باشد. اگر شمارش با گزارش پنل فرق دارد یا `SENDING` صفر نیست، اعمال نکنید. مقدار `pending_digest` همان خروجی را در فرمان زیر جایگزین `DIGEST` کنید؛ مقدار `N` نیز باید از خروجی تازهٔ خود سرور برداشته شود:

```bash
MARKET_ACCESS_V2_ENABLED=True /srv/trading-platform/venv/bin/python manage.py cancel_trial_day_three_sms_20261029 --actor superadmin --apply --confirm-worker-stopped --expected-pending-count N --expected-pending-digest DIGEST
```

پس از اجرا `cancelled_now=N` را تأیید کنید و پیش‌نمایش را دوباره بگیرید؛ `pending_to_cancel` باید صفر باشد. تایمر را هنوز روشن نکنید. متن روز سوم در پنل «مسیر هفت‌روزه» قابل ویرایش است، اما ویرایش آن پیام‌های لغوشده را خودکار دوباره صف نمی‌کند. تصمیم دربارهٔ ارسال متن جدید به ۴۵۱۶ نفرِ ارسال‌نشده یا ارسال مجدد به ۳۹۹ نفرِ قبلاً مخاطب، مرحلهٔ جداگانه‌ای با تأیید صریح است.
