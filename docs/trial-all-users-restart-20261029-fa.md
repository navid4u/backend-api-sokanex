# اجرای یک‌بارهٔ Trial هفت‌روزه برای همهٔ کاربران عادی

این عملیات استثنای صریحِ قرارداد «یک Trial در عمر حساب» است و فقط با کلید ثابت `all_normal_users_2026_10_29` یک‌بار قابل اجراست. زمان شروع واقعی، لحظهٔ اجرای دستور `--apply` در سرور است؛ تاریخچهٔ قبلی حذف نمی‌شود. کاربر دارای Trial فعال V2 (شروع‌شده، منقضی‌نشده، لغونشده) کاملاً دست‌نخورده می‌ماند. سایر کاربران عادی، حتی با Trial قبلی/باطل‌شده، یک Grant تازه دقیقاً هفت‌روزه می‌گیرند. سوپرادمین و پشتیبانی مستثنی‌اند. دسترسی‌های بازار و وضعیت ELITE قبلیِ همین گروه مطابق تأیید مالک لغو می‌شوند؛ انتخاب بازار، نقش، کیف پول و حساب کاربری تغییر نمی‌کنند. حساب غیرفعال هم Grant می‌گیرد ولی تا فعال شدن SMS/اعلان دریافت نمی‌کند.

ثبت‌نام‌های آینده از تنظیم موجود `TrialAutoStartSettings` استفاده می‌کنند؛ این عملیات آن را تغییر نمی‌دهد. برای SMS/اعلان، Grantهای جدید در Journey فعلی ثبت می‌شوند. کارگر `sokanex-sms-automation` پیام‌های روزانه را طبق قواعد فعال صف و ارسال می‌کند. در مقیاس چند هزار کاربر، ارسال روز اول تدریجی است؛ پیامک‌ها را فقط بر اساس `SENT` و شناسهٔ ارائه‌دهنده «ارسال‌شده» بدانید، نه بر اساس `queued`.

## پیش‌نیاز و استقرار

روی production، قبل از مهاجرت/اجرا از دیتابیس و سرور بکاپ معتبر بگیرید و نتیجهٔ سرویس بکاپ را بررسی کنید. فایل‌های ناشناس و `.secrets/` در checkout سرور را حذف/commit نکنید. سرویس‌ها و نسخهٔ deploy را کنترل کنید:

```bash
cd /srv/trading-platform/backend
systemctl start trading-platform-backup.service
systemctl show trading-platform-backup.service -p Result -p ExecMainStatus --no-pager
git status --short
git fetch origin backend-with-frontedits
git merge --ff-only origin/backend-with-frontedits
git rev-parse --short HEAD
/srv/trading-platform/venv/bin/python manage.py check
/srv/trading-platform/venv/bin/python manage.py migrate --plan
/srv/trading-platform/venv/bin/python manage.py migrate --noinput
/srv/trading-platform/venv/bin/python manage.py migrate --check
systemctl restart trading-platform.service
sleep 5
curl -fsS --max-time 15 http://127.0.0.1:8000/api/health/
```

پیش از اجرای انبوه، `MARKET_ACCESS_V2_ENABLED=True` و `TRIAL_JOURNEY_ENABLED=True` در محیط واقعی سرویس API و کارگر، فعال بودن تایمر، وضعیت تنظیم ثبت‌نام جدید و فعال بودن Day 1 را بررسی کنید. مقدار `TRIAL_JOURNEY_ENABLED` معمولاً از systemd می‌آید؛ خالی بودن آن در shell کاربر root به‌تنهایی نشان‌دهندهٔ خاموش بودن کارگر نیست.

```bash
pid=$(systemctl show -p MainPID --value trading-platform.service)
tr '\0' '\n' < "/proc/$pid/environ" | grep -E '^(MARKET_ACCESS_V2_ENABLED|TRIAL_JOURNEY_ENABLED|SMS_AUTOMATION_ENABLED)='
systemctl show sokanex-sms-automation.service -p Environment -p EnvironmentFiles --no-pager
systemctl is-active sokanex-sms-automation.timer
/srv/trading-platform/venv/bin/python manage.py shell -c "from apps.notifications.models import TrialJourneyActivation, TrialJourneyDay; from apps.accounts.models import TrialAutoStartSettings; s=TrialAutoStartSettings.objects.filter(pk=1).first(); print({'auto_start_new_users':bool(s and s.auto_start_new_users and s.campaign_id),'journey_activated':TrialJourneyActivation.objects.filter(pk=1).exists(),'day1_active':TrialJourneyDay.objects.filter(day=1,is_active=True).exists()})"
```

اگر هر سه مقدار آخر `True` نیستند، **اجرا را متوقف کنید**؛ تنظیمات را بدون بازبینی وضعیت واقعی تغییر ندهید.

## پیش‌نمایش و اجرای تأییدشده

خروجی اول فقط شمارش و fingerprint مبهم می‌دهد، نه فهرست شخصی کاربران. پیش‌نمایش را به مالک نشان دهید و مطمئن شوید `already_applied=false`، تعداد کاربران و لغو دسترسی‌ها مطابق انتظار است. `N` و `SHA256` را دقیقاً از همان خروجی بگذارید؛ از نمونهٔ راهنما کپی نکنید.

```bash
MARKET_ACCESS_V2_ENABLED=True /srv/trading-platform/venv/bin/python manage.py restart_all_users_trial_20261029 --actor superadmin
MARKET_ACCESS_V2_ENABLED=True /srv/trading-platform/venv/bin/python manage.py restart_all_users_trial_20261029 --actor superadmin --apply --confirm-restart-all-users --expected-eligible-count N --expected-candidate-digest SHA256
```

اگر بین پیش‌نمایش و اجرا cohort تغییر کند، دستور بدون نوشتن داده خطای conflict می‌دهد؛ مجدداً پیش‌نمایش بگیرید. پس از موفقیت، اجرای مجدد `already_applied=true` می‌دهد و هیچ Grant اضافه یا تمدید نمی‌کند. اگر snapshot قبل از اجرا restore شود، اثر اجرا هم از بین می‌رود و باید فقط بعد از بازبینی کامل وضعیت بازیابی تصمیم بگیرید.

## راستی‌آزمایی پس از اجرا

```bash
/srv/trading-platform/venv/bin/python manage.py shell -c "from apps.accounts.models import TrialCampaign,TrialGrant,User; from apps.notifications.models import TrialJourneyEnrollment; c=TrialCampaign.objects.get(operation_key='all_normal_users_2026_10_29'); q=TrialGrant.objects.filter(campaign=c); print({'campaign_status':c.status,'grants':q.count(),'seven_day_grants':sum((g.ends_at-g.started_at).days==7 for g in q.iterator()),'journey_enrollments':TrialJourneyEnrollment.objects.filter(grant__campaign=c).count(),'special_user_grants':q.filter(user__is_superuser=True).count()})"
systemctl start sokanex-sms-automation.service
systemctl show sokanex-sms-automation.service -p Result -p ExecMainStatus --no-pager
journalctl -u sokanex-sms-automation.service -n 15 --no-pager
systemctl is-active sokanex-sms-automation.timer
```

در صورت وجود کاربران غیرفعال، تعداد `journey_enrollments` می‌تواند شامل آنان باشد ولی SMS برایشان `SKIPPED` شود. وضعیت‌های صف/SENT/FAILED را از گزارش ارسال پنل یا مدل تحویل کنترل کنید. سلامت `/api/health/` به‌تنهایی اثبات ارسال SMS یا دسترسی درست نیست. با یک کاربر مجازِ بدون Trial فعال قبلی، وضعیت Trial در dashboard/profile و با یک کاربر دارای Trial فعال قبلی، عدم تغییر تاریخ پایان را جداگانه کنترل کنید.
