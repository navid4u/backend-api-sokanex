# دستورالعمل عبور کنترل‌شدهٔ Market Access V2 به staging

این سند برای Phase 9 است، نه مجوز روشن‌کردن V2 روی production. تا وقتی staging مستقل، بک‌آپ بازیابی‌آزمایش‌شده و فرانت سازگار تأیید نشده‌اند، `MARKET_ACCESS_V2_ENABLED=False` بماند. هیچ‌کدام از دستورهای این سند در این checkout روی سرور اجرا نشده‌اند.

## پیش‌شرط‌های توقف/ادامه

1. یک staging با دیتابیس **جدا**، فایل محیطی/کلیدهای جدا و نسخهٔ کد دقیقاً مشخص داشته باشید. صرف اجرای تست SQLite محلی، جای staging PostgreSQL را نمی‌گیرد.
2. پیش از کپی دادهٔ واقعی، ارسال SMS، اعلان، CRM، پرداخت، ایمیل، webhook و jobهای زمان‌بندی‌شدهٔ staging را غیرفعال کنید؛ از staging نباید پیام واقعی به کاربران یا سرویس‌های مالی برود. دسترسی به نسخهٔ بک‌آپ را محدود و رمزنگاری کنید.
3. از production بک‌آپ معمول دیتابیس و رسانه را بگیرید، نتیجهٔ سرویس بک‌آپ را بررسی کنید، **فایل واقعی بک‌آپ** و اندازه/تاریخ آن را تأیید کنید، و restore را روی دیتابیس منزوی آزمایش کنید. `Result=success` به‌تنهایی اثبات restoreپذیری نیست. رمزها/توکن‌ها را در خروجی عمومی یا چت قرار ندهید.
4. نسخهٔ کد و SHA، نسخهٔ migrationها، وضعیت `MARKET_ACCESS_V2_ENABLED` و خروجی دستور فقط‌خواندنی زیر را قبل و بعد از migration نگه دارید. خروجی صرفاً شمارش‌های تجمیعی است و جای بک‌آپ ردیفی را نمی‌گیرد:

```bash
cd /srv/trading-platform/backend
/srv/trading-platform/venv/bin/python manage.py audit_market_access_v2
```

این دستور قبل از migrationهای 0022–0024 نیز کار می‌کند و در آن حالت `v2_tables_present=false` می‌دهد. هیچ نام کاربری، شماره، URL یا token چاپ نمی‌کند.

## اجرای آزمایشی روی staging مستقل

در دستورات زیر مسیر Python و پوشهٔ پروژهٔ staging را با مقدار واقعی آن جایگزین کنید؛ مسیر production را در staging به‌اشتباه اجرا نکنید. بعد از checkout نسخهٔ آزمایشی و با پرچم خاموش:

```bash
python manage.py check
python manage.py showmigrations accounts
python manage.py migrate --plan
python manage.py makemigrations --check --dry-run
python manage.py audit_market_access_v2
python manage.py migrate --noinput
python manage.py check
python manage.py audit_market_access_v2
```

از روی دو snapshot بررسی کنید تعداد کاربران، نقش‌های `SUPER_ADMIN`/`SUPPORT`، superuserها، سطح‌های قدیمی، تاریخ‌های Gold قدیمی و `UpgradeRequest` **بدون تغییر** مانده‌اند. فقط جدول‌های افزایشی V2 ایجاد می‌شوند؛ migrationها نباید سطح کاربر یا مجوز قبلی را بازنویسی کنند. اگر هر شمارش legacy برخلاف انتظار عوض شد، rollout را متوقف و از بک‌آپ بررسی کنید.

سپس فقط در staging، پرچم را روشن و سرویس staging را restart کنید. با JWTهای آزمایشیِ واقعیِ هر نقش، status و JSON این مسیرها را بررسی کنید:

- `GET /api/accounts/profile/details/` و `GET /api/dashboard/`: `market_access_v2` از بک‌اند، همراه با `access_level` قدیمیِ حفظ‌شده.
- `GET/PUT /api/accounts/profile/market-preferences/`: تغییر چک‌باکس‌ها دسترسی واقعی ایجاد نکند.
- `GET /api/accounts/admin/market-access/users/` و `PATCH /api/accounts/admin/market-access/users/{id}/`: فقط مدیر مجاز/Support؛ کاربر عادی 403؛ Level مشتق از grantها.
- `GET/PATCH /api/accounts/admin/market-access/content-policy/`: پیش‌فرض مقاله/ویدئو/لایو برای Level 1 و بالاتر باز باشد؛ تغییر policy فقط از همین مسیر مدیریت اعمال شود.
- `POST /api/accounts/market-access/requests/` و review مدیر: تأیید بازارهای انتخاب‌شده سطح Basic/Pro/Gold متناظر بدهد، درخواست معلق تکراری دوباره ایجاد نشود.
- سیگنال VIP، تحلیل داخلی، آکادمی، دستیار، اعلان و مسیرهای legacy را برای Level 1، Basic، Pro، Gold، Superadmin و Support مقایسه کنید. شرط خرید/مالکیت/انتشار مستقل نباید حذف شده باشد.
- preview کمپین Trial را فقط با Superadmin و دادهٔ آزمایشی بررسی کنید. **اجرای واقعی کمپین** حتی در staging کپی‌شده از production فقط پس از تأیید cohort و غیرفعال‌بودن side effectها مجاز است؛ هر کاربر فقط یک Trial V2 می‌گیرد.

تست‌های `manage.py test` را فقط با دیتابیس تست مجزا اجرا کنید؛ روی DB اصلی staging یا production فرض نکنید که تست‌ها read-only هستند. برای PostgreSQL، نقش تست باید مجوز ساخت دیتابیس تست داشته باشد، یا DB تست مجزا از قبل فراهم شده باشد.

## توقف، rollback و production

- اگر رفتار V2 نامطلوب شد، ابتدا پرچم را `False` و سرویس را restart کنید؛ این rollback **رفتاری** است و جدول‌های V2 را پاک نمی‌کند. با همان smoke testهای endpointهای قدیمی تأیید کنید.
- migrationهای 0022–0024 ساختاراً افزایشی هستند، ولی reverse کردنشان پس از ثبت Preference/Grant/Trial/Request/Audit داده‌های جدید را حذف می‌کند. در production از `migrate accounts 0021` به‌عنوان rollback سریع استفاده نکنید.
- rollback داده فقط با رویهٔ restore آزمایش‌شده و تصمیم آگاهانه دربارهٔ داده‌هایی که از زمان بک‌آپ ایجاد شده‌اند انجام شود؛ restore کل DB ممکن است ثبت‌نام‌ها/پرداخت‌های جدید را از بین ببرد.
- production تنها پس از امضای نتیجهٔ staging، سازگاری فرانت، پنجرهٔ استقرار و برنامهٔ مانیتورینگ مجاز است. ابتدا migration با پرچم خاموش، سپس smoke و مقایسهٔ snapshot؛ روشن‌کردن پرچم یک گام مستقل و قابل توقف باشد.

## IP پرترافیک 31.7.66.189

این IP در تنظیمات/کد فعلی به‌صورت ثابت یافت نشده است. دستور `audit_outbound_ip 31.7.66.189` روی **خود سرور** فقط تطابق DNS فعلی مقصدهای تنظیم‌شده را گزارش می‌کند؛ نتیجهٔ بدون match منبع اتصال تاریخی را رد نمی‌کند. پیش از حذف یا تغییر provider/feed، باید جهت اتصال، فرایند و hostname واقعی در همان زمان از لاگ/metadata سرور معلوم شود. این مراحل قانون block بیرونی موجود را تغییر نمی‌دهند. سقف ۲MiB پاسخ JSON بازار، مصرف فایل بزرگ را کم می‌کند ولی تضمین قطع همهٔ ترافیک به آن IP نیست.
