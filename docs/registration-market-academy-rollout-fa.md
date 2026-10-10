# استقرار کنترل‌شدهٔ ثبت‌نام، انتخاب بازار و آپلود آکادمی

این تغییرات در checkout محلی تست شده‌اند؛ تا اجرای دستورهای زیر، وضعیت production تأیید نشده است. migration `accounts.0025` هیچ دسترسی یا Trial جدیدی نمی‌سازد. فرمان بازتنظیم cohort نیز پیش‌فرض فقط dry-run است و نباید بدون بررسی خروجی، بک‌آپ بازیابی‌پذیر و تصمیم صاحب محصول اجرا شود.

## پیش از migration

از دیتابیس و `MEDIA_ROOT` بک‌آپ بگیرید، تاریخ/اندازهٔ فایل بک‌آپ و امکان restore را روی محیط جدا بررسی کنید. سپس در `/srv/trading-platform/backend` شمار گروه‌های ایمیل تکراری را **بدون چاپ ایمیل** ببینید:

```bash
systemctl start trading-platform-backup.service
systemctl show trading-platform-backup.service -p Result -p ExecMainStatus --no-pager
```

`Result=success` به‌تنهایی آزمون بازیابی نیست؛ مسیر و سلامت فایل بک‌آپ و snapshot رسانه را نیز تأیید کنید.

```bash
/srv/trading-platform/venv/bin/python manage.py shell -c "from django.contrib.auth import get_user_model; from django.db.models import Count; from django.db.models.functions import Lower, Trim; U=get_user_model(); q=U.objects.exclude(email='').annotate(e=Lower(Trim('email'))).values('e').annotate(n=Count('pk')).filter(n__gt=1); print('duplicate_email_groups=', q.count())"
```

اگر خروجی صفر نیست، توقف کنید. migration عمداً ایمیل کاربران را پاک/ادغام نمی‌کند و با پیام غیرحساس متوقف می‌شود. رفع تکراری‌ها نیاز به تصمیم مالک داده دارد. صرف `market_type` قدیمی نشانهٔ انتخاب صریح نیست؛ backfill فقط از ردیف معتبر `UserMarketPreference` انجام می‌شود.

```bash
git fetch origin backend-with-frontedits
git merge --ff-only origin/backend-with-frontedits
/srv/trading-platform/venv/bin/python manage.py check
/srv/trading-platform/venv/bin/python manage.py makemigrations --check --dry-run
/srv/trading-platform/venv/bin/python manage.py migrate --plan
/srv/trading-platform/venv/bin/python manage.py migrate --noinput
/srv/trading-platform/venv/bin/python manage.py showmigrations accounts
/srv/trading-platform/venv/bin/python manage.py showmigrations platform_settings
/srv/trading-platform/venv/bin/python manage.py shell -c "from django.core.cache import cache; cache.delete('platform:translations:en:v1')"
/srv/trading-platform/venv/bin/python manage.py restart_market_access_v2_cohort
```

خروجی آخر باید `mode: dry_run` باشد. گزارش فقط شمارش است: کاربران عادی، کاربران ویژهٔ مستثنا، grantهای V2 به تفکیک source، Trialهای فعال V2، Elite، و درخواست‌های legacy تأییدشده. هیچ داده‌ای در dry-run تغییر نمی‌کند. از روی `legacy_access_level` کاربر معمولی در V2 سطح ساخته نمی‌شود، اما فیلد/سوابق قدیمی برای rollback رفتاری حفظ می‌شوند.

در فرانت، فقط `market_access_v2.membership_tier`، `approved_markets`، `effective_markets` و `trial_active` را برای نمایش سطح/دسترسی V2 ملاک بگیرید؛ `access_level` قدیمیِ top-level برای سازگاری باقی می‌ماند و ممکن است هنوز ۵ باشد. `market_selection_confirmed` پس از PUT موفق در دیتابیس دائمی است و نباید از claim قدیمی JWT یا state محلی استنتاج شود. پاسخ dashboard در `data.market_access_v2` و پاسخ profile/details در `market_access_v2` است.

ثبت‌نام ایمیل/رمز در `/api/accounts/register/` JWT را در `tokens.access` و `tokens.refresh` برمی‌گرداند. ورود بعدی همچنان با `username` یا شمارهٔ موجود مطابق قرارداد فعلی انجام می‌شود؛ login با email و OTP ایمیل در این تغییر ساخته نشده‌اند. مسیرهای `auth/registration/request/` و `auth/registration/verify/` OTP پیامکی قبلی را حفظ می‌کنند.

## تصمیم جداگانهٔ بازتنظیم cohort

اگر واقعاً باید دسترسی‌های V2 فعلیِ همهٔ کاربران عادی از نو آغاز شود، پس از مرور dry-run و تأیید مالک داده، فقط در پنجرهٔ استقرار این فرمان را اجرا کنید:

```bash
/srv/trading-platform/venv/bin/python manage.py restart_market_access_v2_cohort --apply --confirm-v2-trials-remain-used
```

فرمان کاربران `is_superuser`، `SUPER_ADMIN` و `SUPPORT` را کنار می‌گذارد، grantهای فعال V2 را با `revoked_at` غیرمؤثر می‌کند، Elite را برمی‌دارد و Trial فعال V2 را با `revoked_at` خاتمه می‌دهد. هیچ `TrialGrant`، `UpgradeRequest`، تأیید یا ترجیح بازار حذف نمی‌شود. هر حساب تغییرکرده یک audit با علت `V2_COHORT_RESTART` می‌گیرد. **Trial V2 قبلاً استفاده‌شده همچنان استفاده‌شده است؛ اجرای مجدد کمپین به آن حساب Trial دوم نمی‌دهد.** اجرای دوبارهٔ فرمان نباید audit تکراری بسازد. هیچ کمپین، SMS یا شارژ کیف پول از این فرمان آغاز نمی‌شود.

اگر قصد شروع Trial تازه برای کاربران واجد شرایط دارید، فقط API موجود `trial-campaigns/preview/` و پس از بررسی digest/cohort، API اجرای کمپین با JWT سوپرادمین را استفاده کنید. این قدم مستقل از migration و reset است.

## آپلود آکادمی در زیرساخت واقعی

در کد، `cover_image` و `Session.image` حداکثر ۸ MiB و `video_file` حداکثر ۵۰۰ MiB دارند؛ پسوند و Content-Type بررسی می‌شود، ImageField تصویر را decode/validate می‌کند و امضای ابتدایی ظرف ویدئو (MP4/MOV یا EBML) نیز کنترل می‌شود. `FILE_UPLOAD_PERMISSIONS=0644` و `FILE_UPLOAD_DIRECTORY_PERMISSIONS=0755` است. اندازه/timeout واقعی reverse proxy را از تنظیمات سرور و سرویس Gunicorn بخوانید؛ تست محلی آن را اثبات نمی‌کند. برای فایل ۵۰۰ MiB، سقف بدنهٔ پراکسی باید بیش از ۵۰۰ MiB باشد، و timeout مسیر آپلود با timeout ۱۸۰ ثانیه‌ای فرانت هماهنگ شود. در لاگ کاربر، Gunicorn قبلاً `--timeout 60` بوده؛ این مقدار برای آپلود بزرگ ممکن است ۵۰۲ بدهد و باید با سنجش زیرساخت اصلاح شود، نه با تغییر حدسی کد.

```bash
systemctl cat trading-platform.service
systemctl is-active nginx apache2
nginx -T 2>/dev/null | grep -E 'client_max_body_size|proxy_(read|send)_timeout' | head -n 30
apachectl -t -D DUMP_RUN_CFG 2>/dev/null | head -n 30
namei -l /srv/trading-platform/backend/media
```

روی سرور، یک دوره و جلسهٔ آزمایشی با JWT مدرس/مدیر بسازید، POST و PATCH واقعی multipart را با تصویر/ویدئوی نمونه اجرا کنید، URL بازگشتی media را با GET آزمایش کنید، و مجوز نوشتن `tradingapp` روی `MEDIA_ROOT` را بررسی کنید. در درخواست multipart هدر `Content-Type` را دستی با boundary ناقص تعیین نکنید. `allowed_levels` باید به‌صورت کلید تکراری فرستاده شود. `video_url=` همراه `video_file=@...` URL قبلی را پاک می‌کند؛ PATCH بدون فایل باید فایل قبلی را نگه دارد. هیچ token یا فایل خصوصی را در خروجی عمومی قرار ندهید.

پس از تأیید migration و پیکربندی proxy/storage، سرویس را restart و health و endpointهای اصلی را با کاربر آزمایشی authenticated بررسی کنید. migration `platform_settings.0003` واژه‌نامهٔ ۱۴۱۵ کلیدی فرانت موجود را در catalog انگلیسی ثبت می‌کند؛ کلیدهای از پیش تنظیم‌شده توسط مدیر را بازنویسی نمی‌کند. پس از استقرار، `GET /api/platform/translations/en/` باید دست‌کم ۱۴۱۵ کلید برگرداند. چون UI ممکن است مستقل از این نسخه تغییر کند، کلیدهای افزودهٔ آینده باید در فرایند انتشار هماهنگ شوند؛ این seed ادعای ترجمهٔ خودکار همهٔ متن‌های آینده ندارد.

خطاهای DRF علاوه بر `errors` متن‌دار، `error_codes` متناظر را نیز به‌صورت افزایشی برمی‌گردانند تا فرانت بتواند پیام‌های validation/permission را با ترجمهٔ UI خود نمایش دهد. هیچ متن کاربر یا محتوای پست به‌شکل خودکار ترجمه نمی‌شود. مقدار خالی برای ترجمهٔ انگلیسی جدید رد می‌شود؛ این اعتبارسنجی به‌تنهایی کامل‌بودن کلیدهای فرانت را ثابت نمی‌کند.
