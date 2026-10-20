# شروع خودکار Trial، گزارش SMS و بازدید صفحه — قرارداد و راستی‌آزمایی

این سند برای کد جدید است، نه تأیید وضعیت production. تا وقتی migration، worker و تنظیمات واقعی سرور بررسی نشوند، ثبت‌نام موفق یا health=200 دلیل شروع Trial، ارسال پیامک یا ثبت بازدید نیست. شماره/توکن/API key را در خروجی عمومی یا تیکت قرار ندهید.

## منطق جدید و دلیل خطاهای قبلی

- پیش‌تر Trial در بعضی مسیرها هنگام ایجاد حساب، پیش از ساخت نشست موفق آغاز می‌شد. اکنون ثبت‌نام رمزی/ایمیلی و OTP هنگام صدور موفق نشست از سرویس مشترک استفاده می‌کنند. درخواست OTP، ایجاد خام User و ثبت‌نام ناموفق، Trial/Welcome نمی‌سازند. بازکردن مجدد dashboard، refresh token و ورودهای بعدی نیز Trial را تمدید نمی‌کنند.
- تنظیم `GET/PATCH /api/accounts/admin/market-access/trial-settings/` فقط با انتخاب مدیر روشن می‌شود. V2، تنظیم شروع خودکار و cutoff زمان روشن‌کردن باید برقرار باشند. کاربران قدیمی، Trial استفاده‌شده و نقش‌های محافظت‌شده مجدداً ثبت‌نام آزمایشی نمی‌شوند. تصمیم نخستین نشست در `TrialAutoStartDecision` و `UserAccessAudit` ثبت می‌شود؛ علت‌هایی مانند `AUTO_START_DISABLED`, `V2_DISABLED`, `EXISTING_ACCOUNT`, `TRIAL_ALREADY_USED`, `PROTECTED_ROLE` قابل مشاهده‌اند. دادهٔ قبلی حذف نمی‌شود.
- پاسخ مدیریت `GET /api/accounts/admin/market-access/users/` در `access` فیلدهای `trial_status`, `trial_started_at`, `trial_ends_at`, `trial_source`, `trial_start_blocked_reason` را از رکورد واقعی می‌دهد. `trial_status` یکی از `NOT_STARTED`, `ACTIVE`, `EXPIRED`, `CANCELED` است؛ source قدیمیِ نامعلوم `null` باقی می‌ماند. این داده‌ها فقط با مجوز فعلی مدیریت V2 دیده می‌شوند.
- هر Trial هفت روز دقیق از زمان server-side شروع می‌شود. دسترسی V2 در لحظهٔ پایان از resolver قطع می‌شود؛ worker هر پنج دقیقه رویداد انقضا را فقط یک‌بار audit می‌کند و دسترسی دائمی/Elite را پاک نمی‌کند.
- فعال‌بودن Journey به‌تنهایی ارسال SMS را تضمین نمی‌کند: `TRIAL_JOURNEY_ENABLED`, `SMS_AUTOMATION_ENABLED`, آمادگی Payamito، روز/بازار فعال و شماره معتبر لازم‌اند. Journey روز اول Trial enrolled را در صف ثبت می‌کند؛ WELCOME مجزا در همین حالت با علت `JOURNEY_OWNS_WELCOME` به‌صورت `SKIPPED` ثبت می‌شود تا دو پیام یکسان نرود. اگر روز اول Journey برای آن کاربر فعال/منطبق نیست، WELCOME Rule مستقل می‌تواند کار کند. deliveryهای عدم ارسال علت کوتاه دارند؛ متن و شماره در log سرور نوشته نمی‌شوند. `SENT` یعنی provider درخواست را پذیرفته، نه اینکه رسید تحویل گوشی ثابت شده باشد.
- `TRIAL_7` و روز هفتم Journey زودتر از `trial_ends_at` ارسال نمی‌شوند. Journey و Ruleهای قدیمی Trial هم‌زمان scheduler مستقل ندارند؛ با فعال‌سازی Journey، Ruleهای قدیمی Trial خاموش می‌مانند. Rule WELCOME را می‌توان مستقل برای کاربران غیر-enrolled فعال کرد. رکورد `SENDING` مبهم خودکار retry نمی‌شود.
- `GET /api/notifications/sms-automation/deliveries/?user_id=<ID>` همهٔ پنج وضعیت را نشان می‌دهد. `rendered_text` snapshot همان ارسال و `error_code` علت عدم ارسال/شکست است. `ordering` می‌تواند `created_at`, `-created_at`, `sent_at`, `-sent_at` باشد. فیلترها قبل از pagination اعمال می‌شوند؛ شناسهٔ provider خام محرمانه نیست، اما credential/پاسخ خام provider برنمی‌گردد.
- `GET /api/dashboard/` مقدار واقعی `data.analytics_tracking.enabled` را از `ANALYTICS_PAGE_VIEW_TRACKING_ENABLED` می‌گیرد. پیش‌فرض خاموش است. وقتی روشن شود، POST معتبر `POST /api/activity/page-views/` رویداد را در DB ذخیره می‌کند و overview مدیریتی آن را از aggregate واقعی نشان می‌دهد. history قبل از فعال‌سازی ساخته نمی‌شود. جزئیات مسیرهای canonical و retention در `docs/admin-analytics-rollout-fa.md` آمده است.

## استقرار با backup و بدون ارسال ناخواسته

قبل از اجرا، snapshot و backup قابل‌بازیابی را تأیید کنید. فایل‌های محلی ناشناس/secret در production را حذف یا commit نکنید. روی checkout production:

```bash
cd /srv/trading-platform/backend
git status --short
systemctl start trading-platform-backup.service
systemctl show trading-platform-backup.service -p Result -p ExecMainStatus --no-pager
git fetch origin backend-with-frontedits
git merge --ff-only origin/backend-with-frontedits
/srv/trading-platform/venv/bin/python manage.py check
/srv/trading-platform/venv/bin/python manage.py makemigrations --check --dry-run
/srv/trading-platform/venv/bin/python manage.py migrate --plan
```

Plan باید فقط migration افزایشی `accounts.0029_trial_session_decision` و migrationهای قبلاً اعمال‌نشدهٔ مشروع را نشان دهد. سپس:

```bash
/srv/trading-platform/venv/bin/python manage.py migrate --noinput
/srv/trading-platform/venv/bin/python manage.py migrate --check
systemctl restart trading-platform.service
sleep 5
systemctl is-active trading-platform.service
curl -fsS --max-time 15 https://api.sokanex.com/api/health/
systemctl is-active sokanex-sms-automation.timer
systemctl show sokanex-sms-automation.service -p Result -p ExecMainStatus --no-pager
```

`systemctl show ... -p Environment --value` را به‌صورت کامل منتشر نکنید؛ ممکن است secret داشته باشد. در خروجی قابل‌اشتراک فقط boolean تنظیمات را چاپ کنید. Trial را با تغییر تنظیمات مدیر/فعال‌سازی Ruleها خودسرانه روشن نکنید. اگر timer غیرفعال است، ابتدا دلیل آن و آخرین journal را بررسی کنید؛ بدون آماده‌بودن provider و سیاست ارسال روشنش نکنید. `process_sms_automation` اکنون audit انقضا را نیز انجام می‌دهد؛ اجرای دستی آن ممکن است SMSهای واقعاً pending را بفرستد، پس صرفاً برای تست تشخیصی اجرا نشود.

## راستی‌آزمایی بدون افشای شماره

برای پیدا کردن شناسهٔ حساب آزمایشی بدون گذاشتن شماره در history، در ترمینال تعاملی سرور `manage.py shell` را اجرا کنید و ورودی شماره را با `getpass` پنهان بگیرید. هیچ دستور زیر SMS نمی‌فرستد:

```bash
cd /srv/trading-platform/backend
/srv/trading-platform/venv/bin/python manage.py shell
```

```python
from getpass import getpass
from django.conf import settings
from apps.accounts.models import User, TrialAutoStartSettings, TrialAutoStartDecision, TrialGrant
from apps.notifications.models import SMSAutomationDelivery, SMSAutomationRule, TrialJourneyActivation
from apps.accounts.market_access import market_access_v2_enabled
from common.phone import normalize_iran_phone
phone = normalize_iran_phone(getpass('Test account phone (hidden): '))
u = User.objects.filter(phone=phone).first()
print({'found': bool(u), 'user_id': u.pk if u else None})
phone = None
if u:
    decision = TrialAutoStartDecision.objects.filter(user=u).first()
    grant = TrialGrant.objects.filter(user=u, invalidated_at__isnull=True).first()
    print({'v2': market_access_v2_enabled(), 'auto_start': TrialAutoStartSettings.objects.filter(pk=1, auto_start_new_users=True).exists(), 'trial_decision': decision.reason if decision else None, 'grant_id': grant.pk if grant else None, 'grant_source': grant.source if grant else None, 'trial_started_at': grant.started_at.isoformat() if grant else None, 'trial_ends_at': grant.ends_at.isoformat() if grant else None})
    print({'sms_enabled': settings.SMS_AUTOMATION_ENABLED, 'provider_configured': bool(settings.PAYAMITO_ENABLED and settings.PAYAMITO_USERNAME and settings.PAYAMITO_API_KEY and settings.PAYAMITO_FROM_NUMBER), 'journey_enabled': settings.TRIAL_JOURNEY_ENABLED, 'journey_activated': TrialJourneyActivation.objects.filter(pk=1).exists(), 'enabled_rules': SMSAutomationRule.objects.filter(enabled=True).count(), 'analytics_enabled': settings.ANALYTICS_PAGE_VIEW_TRACKING_ENABLED})
    print(list(SMSAutomationDelivery.objects.filter(user=u).values('id','event','status','failure_code','scheduled_at','sent_at').order_by('-created_at')[:20]))
```

فقط همین خروجی بدون شماره/متن/توکن را به پشتیبانی بدهید. نبودن `TrialAutoStartDecision` برای حساب قدیمی پیش از استقرار طبیعی است؛ تصمیم جدید فقط روی نخستین نشستِ ثبت‌نام پس از استقرار ثبت می‌شود. برای اثبات فرایند جدید یک حساب آزمایشی **جدید** لازم است، نه صرفاً حساب قبلی.

در محیط آزمونِ جدا از production، با provider stub مسیر ثبت‌نام رمزی/ایمیلی و OTP، یک `PENDING` یا `SKIPPED` دارای علت، اجرای worker، سپس `SENT` را بررسی کنید. آزمون پیامک واقعی فقط با رضایت مالک و یک مخاطب مجاز انجام شود. برای page view ابتدا flag را خاموش نگه دارید و POST بدون write (`202`) را ببینید؛ بعد از تأیید privacy و فعال‌کردن flag در سرویس API، dashboard باید `true` بگوید، POST معتبر یک‌بار `201` و تکرارش `200` بدهد و پس از حداکثر ۶۰ ثانیه overview افزایش واقعی نشان دهد. هیچ‌کدام را از health=200 نتیجه نگیرید.

بازگشت رفتاری: ابتدا `auto_start_new_users` و دو flag `SMS_AUTOMATION_ENABLED` و `ANALYTICS_PAGE_VIEW_TRACKING_ENABLED` را طبق اختیار مدیر خاموش کنید؛ برای worker پرریسک timer را متوقف کنید. سپس کد را به commit قبلی برگردانید. migration افزایشی دادهٔ قبلی را حذف نمی‌کند؛ برای rollback ساختاری فقط backup بازیابی‌آزموده‌شده استفاده شود، نه reverse کور migration. Trialهای معتبر و deliveryهای موجود را پاک نکنید.
