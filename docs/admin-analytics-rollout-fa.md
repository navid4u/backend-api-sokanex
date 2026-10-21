# آمار واقعی پنل مدیریت: قرارداد و استقرار

این تغییر در کد محلی پیاده‌سازی شده است؛ تا اجرای مراحل زیر، نصب روی production و صحت دادهٔ واقعی آن تأیید نشده است. endpointهای قبلی حذف نشده‌اند.

## قرارداد API

- `GET /api/accounts/users/?page=1&page_size=20&ordering=-created_at`: همان لیست مدیریت کاربران با `count` واقعی، تاریخ `created_at` و مرتب‌سازی تاریخ ثبت‌نام. دسترسی مطابق مجوز مدیریت کاربران موجود است. کاربران غیرفعال هم در شمار کل هستند مگر فیلتر شوند؛ `page_size` حداکثر ۱۰۰ است.
- `GET /api/accounts/admin/analytics/overview/?period=6m`: فقط SUPER_ADMIN یا superuser. بازه‌های مجاز `1m`, `3m`, `6m`, `12m`, `7d`, `30d`؛ بازهٔ پیش‌فرض شش ماه. ماه‌ها و روزها با منطقهٔ زمانی تهران و ماه‌های شمسی محاسبه می‌شوند؛ بازهٔ بی‌داده نیز صفر برمی‌گرداند. پاسخ `total_users`, `registrations`, `distributions.markets`, `distributions.tiers`, `page_views`, `user_events` و `metadata` دارد.
- `POST /api/activity/page-views/`: تنها برای کاربر احرازشده، وقتی ردیابی فعال باشد. بدنه: `{"event_id":"<UUID>","session_id":"<UUID>","path":"/signals"}`. هر `event_id` را برای یک رویداد ثابت نگه دارید؛ تکرار همان رویداد `200` و ایجاد `201` می‌دهد. بیشتر از ۶۰ درخواست در دقیقه برای هر کاربر، حتی تکرار همان شناسه، `429` است. هنگام خاموش بودن feature، پاسخ `202 {"enabled":false}` و هیچ write ندارد.
- پاسخ موجود `GET /api/dashboard/` در `data.analytics_tracking.enabled` وضعیت واقعی فعال‌سازی را نشان می‌دهد: هم flag سرور باید روشن باشد و هم هر سه جدول event/aggregate/receipt باید موجود باشند. فرانت فقط در صورت `true` رویداد بفرستد. هنگام خاموشی یا آماده‌نبودن جدول‌ها، ingest پاسخ `202 {"enabled":false}` می‌دهد و داده‌ای نمی‌نویسد.

مسیر صفحه باید مقدار ثابت canonical باشد، نه URL واقعی یا شناسهٔ محتوا. مقادیر مجاز در `apps/activity/serializers.py` ثبت شده‌اند؛ نمونه‌ها `/dashboard`, `/signals`, `/academy`, `/academy/:item`, `/articles/:item`. query string، hash، نام کاربر، slug واقعی، IP و دادهٔ محرمانه در رویداد نفرستید. `session_id` یک UUID تصادفیِ عمر نشست مرورگر باشد، نه شماره تلفن یا شناسهٔ احراز هویت. فرانت خطاهای شبکه، ۴۰۰ و ۴۲۹ مربوط به telemetry را بی‌صدا مدیریت کند و برایشان toast یا خطای Observability جدید نسازد. برای ثبت دقیق، رویداد را بعد از نمایش واقعی route و با `event_id` پایدار در retry بفرستد.

`total_users` همهٔ کاربران ثبت‌شده، از جمله غیرفعال‌ها، را در تمام عمر سیستم می‌شمارد. توزیع بازار از فیلد فعلی `market_type` و دستهٔ «انتخاب نشده» است. در V2 روشن، tier از grantهای فعال و پرچم Elite واقعی محاسبه می‌شود و حساب مدیریتی یک دستهٔ مستقل است؛ در V2 خاموش، `access_level` قدیمی با برچسب legacy شمرده می‌شود. رویدادهای اخیر فقط فعالیت‌های ثبت‌شدهٔ واقعی و allowlist‌شده‌اند؛ هیچ متن آزاد، metadata، شماره تماس یا URL خصوصی در آن‌ها منتشر نمی‌شود. `metadata` منبع tier، تعریف مخرج‌ها، زمان شروع پوشش بازدید و نبود backfill تاریخی را توضیح می‌دهد.

نمونهٔ ساختگی و پاک‌سازی‌شدهٔ پاسخ (تعداد bucketها در پاسخ واقعی تابع `period` است):

```json
{
  "period": "1m",
  "timezone": "Asia/Tehran",
  "generated_at": "2026-10-18T09:00:00Z",
  "total_users": 3,
  "registrations": [{"date": "2026-09-23T00:00:00+03:30", "label": "مهر ۱۴۰۵", "count": 1}],
  "distributions": {
    "markets": [{"label": "بازار داخلی", "count": 1}, {"label": "فارکس", "count": 0}, {"label": "کریپتو", "count": 1}, {"label": "انتخاب نشده", "count": 1}],
    "tiers": [{"label": "سطح اولیه", "count": 2}, {"label": "حساب مدیریتی", "count": 1}]
  },
  "page_views": {"total_views": 0, "unique_users": 0, "results": []},
  "user_events": [],
  "metadata": {"tier_source": "market_access_v2", "page_view_coverage_started_at": null, "page_view_history_backfilled": false}
}
```

در پاسخ واقعی، آرایهٔ tiers تمام برچسب‌ها را حتی با صفر دارد و metadata فیلدهای توضیحی و retention بیشتری برمی‌گرداند.

بازدید صفحه از جدول اختصاصی و تجمیع روزانه بر اساس کاربر/مسیر/روز تهران شمرده می‌شود؛ `unique_users` در هر بازه از کاربرهای متمایز واقعی حساب می‌شود، نه جمع اعداد متمایز روزها. rawهای تجمیع‌شده بعد از ۳۰ روز و aggregate و دفترچهٔ idempotency بعد از ۴۰۰ روز با فرمان نگهداری پاک می‌شوند. این آمار قبل از فعال‌سازی وجود ندارد؛ `page_view_history_backfilled=false` را در UI محترم بشمارید. cache سروری overview حداکثر ۶۰ ثانیه است، اما با ثبت یک event جدید کلید cache بر اساس آخرین شناسهٔ event عوض می‌شود تا حتی cache غیرمشترک workerها هم مقدار صفر قدیمی را برنگرداند.

## استقرار مرحله‌ای

۱. از پایگاه داده backup بازیابی‌پذیر و از checkout فعلی snapshot بگیرید. وضعیت backup و امکان restore را بررسی کنید. هیچ فرمان reset cohort، purge observability، یا ارسال SMS جزو این استقرار نیست.

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

۲. بعد از بررسی اینکه plan فقط migrationهای جدید `activity` و ایندکس `accounts.0028` را دارد، migration را اعمال و API را restart کنید. ردیابی در این مرحله هنوز خاموش است.

```bash
/srv/trading-platform/venv/bin/python manage.py migrate --noinput
/srv/trading-platform/venv/bin/python manage.py migrate --check
systemctl restart trading-platform.service
sleep 5
systemctl is-active trading-platform.service
curl -fsS --max-time 15 https://api.sokanex.com/api/health/
```

۳. با حساب سوپرادمین واقعی و توکن فقط در محیط امن خودتان overview را درخواست کنید. پاسخ کاربر عادی باید `403`، کاربر ناشناس `401`، و period نامعتبر `400` باشد. `total_users` را با شمار دیتابیس، جمع tierها را با `total_users` و `page_views` صفر/پوشش تازه را با واقعیت rollout مقایسه کنید. توکن را در تاریخچهٔ shell یا تیکت منتشر نکنید.

۴. قبل از روشن‌کردن ردیابی، متن حریم خصوصی و نقشهٔ routeهای فرانت را تأیید کنید. متغیر `ANALYTICS_PAGE_VIEW_TRACKING_ENABLED=True` را در drop-in سرویس API ثبت کنید، `systemctl daemon-reload` و سرویس را restart کنید. `data.analytics_tracking.enabled` باید `true` شود. از یک حساب تست رویداد canonical بفرستید؛ یک بار `201`، retry همان event `200`، و سپس overview با تأخیر cache حداکثر ۶۰ ثانیه تغییر کند. اگر telemetry مشکل ساخت، فقط این flag را دوباره `False` کنید و سرویس را restart کنید؛ دادهٔ قبلی دست‌نخورده می‌ماند.

۵. تنها پس از صحت migration، timer نگهداری را نصب کنید. قبل از اجرای واقعی، dry-run را بررسی کنید:

```bash
/srv/trading-platform/venv/bin/python manage.py purge_page_view_analytics
install -m 0644 deployment/systemd/sokanex-page-view-retention.service /etc/systemd/system/
install -m 0644 deployment/systemd/sokanex-page-view-retention.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now sokanex-page-view-retention.timer
systemctl list-timers --all --no-pager | grep sokanex-page-view-retention
```

در rollback کد، ابتدا feature flag و timer جدید را خاموش کنید، سپس snapshot کد را برگردانید. migrationها جدول‌های analytics و ایندکس‌های تاریخ می‌سازند، بدون تغییر مقدار حساب، اشتراک یا کیف پول؛ بازگردانی دیتابیس تنها با backup آزموده‌شده انجام شود. حذف جدول‌های analytics برای rollback لازم نیست. production از این محیط محلی مستقیماً تغییر داده نشده است.
