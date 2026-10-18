# انتشار افزایشی قرارداد ۱۷ اکتبر ۲۰۲۶

این راهنما فرمان تولیدی نیست. ابتدا snapshot و backup پایگاه داده و media را روی سرور بگیرید و امکان restore را با اپراتور تأیید کنید. هیچ تستی را به دیتابیس production وصل نکنید. کد این تغییر در محیط محلی با SQLite تست می‌شود؛ اجرای migration یا ارسال واقعی روی production در زمان توسعه انجام نشده است.

## ترتیب امن

1. نسخه Git و وضعیت فایل‌های تغییرکردهٔ سرور را ثبت کنید؛ فایل‌های local/secret را با `git reset --hard` پاک نکنید.
2. از PostgreSQL و `/srv/trading-platform/backend/media` backup قابل بازیابی بگیرید و snapshot سرور را ثبت کنید. در staging با کپی ناشناس‌سازی‌شده migration/test را اجرا کنید.
3. نسخهٔ بک‌اند را با fast-forward دریافت کنید. `manage.py check`، `makemigrations --check --dry-run`، `migrate --plan` و سپس `migrate --noinput` اجرا شود. Migrationها: `accounts.0027`, `content_channels.0005`, `academy.0006`, `notifications.0006`, `signals.0009`.
4. اثر migration پیامک را بررسی کنید: legacy ruleهای `WELCOME`/`TRIAL` غیرفعال و pendingهای همان رویداد `SKIPPED` می‌شوند؛ تاریخچه پاک نمی‌شود. پس از اطمینان از front/backend rollout، با تست کنترل‌شده سناریوی جدید را فعال کنید.
5. `TRIAL_JOURNEY_ENABLED=False` و `VIP_SIGNAL_RETENTION_ENABLED=False` را تا تأیید جداگانه نگه دارید. `SMS_AUTOMATION_ENABLED` نیز باید مطابق سیاست عملیاتی فعلی کنترل شود. هیچ کلید پیامک یا کلید ingest در فرانت قرار نگیرد.
6. سرویس Django را restart و health و OPTIONS با origin اپ را بررسی کنید. GET/PATCH trial-settings، GET/PUT journey و endpointهای invite/holdings را با حساب‌های آزمون و 401/403/200 بررسی کنید؛ HTTP 200 به‌تنهایی اثبات delivery نیست.
7. دوره‌های legacy با `market=''` در V2 برای کاربر عادی پنهان می‌مانند. پیش از طبقه‌بندی، فهرست/تعداد دوره‌های بدون بازار را audit و هر کدام را با تأیید مدیر به internal/forex/crypto تخصیص دهید. تحلیل‌های داخلی قدیمی FOREX خودکار منتقل یا حذف نمی‌شوند.
8. بعد از سلامت بک‌اند، `dist3` فرانت را منتشر کنید و مسیرهای واقعی ثبت‌نام، دعوت، دوره، ویدئو، سیگنال، داشبورد و تنظیمات مدیر را با کاربر آزمون بپیمایید.

مدیر دارای `INTERNAL_ANALYSIS_MANAGE` در فهرست مدیریتی ویدئو فقط ویدئوهای منتشرشده را برای انتخاب راهنما می‌بیند؛ پیش‌نویس‌های تیم ویدئو برای او باز نشده‌اند. ثبت reference فایل کتابخانه را به مالکیت فرصت منتقل نمی‌کند.

گزارش فقط‌خواندنی برای طبقه‌بندی (خروجی شمارش، بدون متن/PII):

```text
python manage.py shell -c "from apps.academy.models import Course; from apps.content_channels.models import ChannelPost; print({'unclassified_courses': Course.objects.filter(market='').count(), 'legacy_internal_forex_posts': ChannelPost.objects.filter(channel__slug='internal-analysis', scope='FOREX').count()})"
```

## فعال‌سازی جداگانهٔ مسیر هفت‌روزه

`GET /api/notifications/sms-automation/journey/` باید ۷ روز seedشده نشان دهد؛ `PUT` فقط برای سوپرادمین است. روزهای ۲ و ۶ پیش‌فرض خاموش‌اند. تنظیم متن/ساعت به‌تنهایی ارسال را روشن نمی‌کند. پس از backup و بررسی قوانین و provider، سوییچ `TRIAL_JOURNEY_ENABLED=True` را فقط در worker مربوطه بگذارید و فرمان زیر را ابتدا بدون flag برای dry-run و سپس با تأیید صریح اجرا کنید:

```text
python manage.py activate_trial_journey
python manage.py activate_trial_journey --apply --confirm
```

فقط TrialGrantهای جدید پس از `activated_at` وارد صف می‌شوند؛ تاریخچهٔ قبلی blast نمی‌شود. worker فعلی `process_sms_automation` صف journey را نیز پردازش می‌کند. برای production ابتدا mock/staging و سپس یک کاربر کنترل‌شده با provider واقعی را بررسی کنید. وضعیت `PENDING/SENDING/SENT/FAILED/SKIPPED` را جداگانه ببینید؛ `SENDING` مبهم را خودکار retry نکنید. برای توقف اضطراری `TRIAL_JOURNEY_ENABLED=False` بگذارید و worker را restart کنید.

نمونهٔ تنظیم غیرمحرمانهٔ systemd برای `sokanex-sms-automation.service`، فقط پس از approval:

```ini
[Service]
Environment="TRIAL_JOURNEY_ENABLED=True"
```

`MARKET_ACCESS_V2_ENABLED=True` و تنظیمات provider باید از سازوکار امن موجود همان worker خوانده شوند؛ کلیدها را در unit، لاگ یا repo کپی نکنید. پیش از activation، محیط مؤثر worker را بدون چاپ مقادیر محرمانه تأیید کنید.

## VIP retention: پیش‌نمایش، نسخهٔ پشتیبان، و فعال‌سازی

فرمان پیش‌فرض فقط تعداد و IDهای حذف‌شوندهٔ هر دو کانال را چاپ می‌کند:

```text
python manage.py prune_vip_signal_channels
```

بعد از backup مستقل DB/media و بررسی dry-run، مسیر absolute جدیدی با دسترسی محدود (نه داخل static/media عمومی) انتخاب کنید. فرمان `--apply` بدون `--confirm` و `--backup-path` اجرا نمی‌شود:

```text
python manage.py prune_vip_signal_channels --apply --confirm --backup-path /secure-backups/vip-prune-YYYYMMDD.zip
```

Zip شامل `vip-posts.json`، `manifest.json` و فایل رسانهٔ رکوردهای حذف‌شده است. رکوردهای هر کانال بر اساس `published_at,created_at,id` جدید به قدیم مرتب می‌شوند و فقط قدیمی‌ترین موارد بالای ۱۰۰ حذف می‌شوند؛ inactive نیز شمرده می‌شود. قفل مجزای کانال جلوی ingest هم‌زمان فراتر از سقف را می‌گیرد. بعد از backup/prune اولیه، سوییچ `VIP_SIGNAL_RETENTION_ENABLED=True` را در سرویس Django فعال و restart کنید تا ingestهای بعدی نیز سقف را رعایت کنند. غیرفعال‌کردن سوییچ جلوی حذف بعدی را می‌گیرد ولی رکوردهای قبلاً حذف‌شده را بازنمی‌گرداند.

نمونهٔ تنظیم غیرمحرمانهٔ `trading-platform.service` پس از بررسی archive:

```ini
[Service]
Environment="VIP_SIGNAL_RETENTION_ENABLED=True"
```

برای rollback دادهٔ حذف‌شده، ابتدا ingestion را متوقف کنید، Zip و snapshot پایگاه داده/رسانه را بررسی کنید، سپس از snapshot کامل restore کنید. بازیابی جزئی از `vip-posts.json` تنها با بررسی تعارض PK/external_id و روابط parent توسط اپراتور DBA انجام شود؛ `loaddata` کور روی production نزنید. فایل‌های orphan فقط پس از commit و در صورت نبود reference به آن نام در هیچ VIP post پاک می‌شوند؛ فایل مشترک باقی می‌ماند.

## API جدید و نمونه‌های sanitized

- `GET/PATCH /api/accounts/admin/market-access/trial-settings/`: `{"auto_start_new_users":true}`، فقط SUPER_ADMIN؛ تغییر سوییچ کاربران قبلی را فعال نمی‌کند.
- `GET/POST /api/accounts/admin/invitation-links/`: POST `{"name":"کمپین الف"}`؛ فهرست استاندارد DRF با `registration_url` و `registrations_count`؛ فقط USER_MANAGE.
- `GET /api/accounts/admin/invitation-links/{id}/registrations/`: کاربران واقعاً ثبت‌شده با `count,next,previous,results`؛ عمومی نیست.
- `GET /api/accounts/admin/users/{user_id}/asset-holdings/`: تنها SUPER_ADMIN، quantity به‌صورت string decimal.
- `GET/PUT /api/notifications/sms-automation/journey/`: `{"days":[{"day":1,"text":"...","is_active":true,"send_time_utc":"09:00:00","market":"ALL","in_app_enabled":true,"push_enabled":true}, ...]}`؛ دقیقاً هفت ردیف.

فرانت فقط `invite_token` اختیاری را به ثبت‌نام موجود اضافه می‌کند؛ لینک دعوت هیچ مجوز ورود نمی‌دهد. خلاصهٔ داشبورد برای کاربر بدون دسترسی عمداً generic است. محتوای کامل VIP و URL رسانهٔ private نباید در projection عمومی برگردد.
