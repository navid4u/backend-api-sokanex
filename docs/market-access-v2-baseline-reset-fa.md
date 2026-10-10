# بازتنظیم یک‌بارهٔ کاربران عادی به سطح ۱

این عملیات **جدا از migration** است. تا اجرای آگاهانهٔ `--apply`، هیچ حساب production تغییر نمی‌کند. فقط کاربران غیر `SUPER_ADMIN`، غیر `SUPPORT` و غیر `is_superuser` هدف هستند؛ نقش‌ها، درخواست‌ها، سوابق Trial و انتخاب‌های قبلی بازار حذف نمی‌شوند.

## نتیجهٔ عملیات

- مقدار واقعی `User.access_level` هر کاربر عادی ۱ می‌شود؛ این فیلد دیگر صرفاً نمای قدیمیِ سطح ۵ باقی نمی‌ماند.
- grantهای فعال V2 و Trialهای فعال/زمان‌بندی‌شدهٔ V2 لغو و Elite پاک می‌شود. `market_access_v2.membership_tier` سپس `LEVEL_1`، `trial_active=false` و `effective_markets=[]` است.
- `market_selection_confirmed_at` پاک می‌شود؛ حتی اگر انتخاب‌های پیشین برای پیش‌پرکردن فرم باقی بمانند، کاربر باید دوباره آن‌ها را با `PUT /api/accounts/profile/market-preferences/` تأیید کند. فرانت باید **فقط** `market_selection_confirmed` را برای نمایش فرم ملاک بگیرد، نه خالی/پر بودن `selected_markets` یا `market_type` قدیمی.
- سوابق `TrialGrant` جدید V2 حذف نمی‌شوند؛ دریافت‌کنندهٔ قبلی V2 طبق قانون یک‌بار در عمر حساب، دوباره واجد Trial نیست. تاریخ‌های Gold قدیمی پیش از V2 در این قانون لحاظ نمی‌شوند. کسانی که `TrialGrant` V2 ندارند، پس از بازتنظیم همچنان می‌توانند در کمپین بعدی مدیر واجد شرایط باشند.
- درخواست V2 معلق قدیمی تا انتخاب دوبارهٔ بازار قابل تأیید نیست. وقتی کاربر بازار را تأیید و درخواست جدیدی ثبت کند، درخواست قدیمی با توضیح سیستمی در تاریخچه می‌ماند و درخواست تازه ساخته می‌شود.
- برای جلوگیری از برگشت ناخواسته به سطح ۵، ذخیرهٔ دوبارهٔ درخواست PREMIUM قدیمی در حالت V2 دیگر سطح را تغییر نمی‌دهد. اگر gate V2 خاموش شود، رفتار legacy مطابق قبل باقی است.

**وابستگی فرانت:** در نسخهٔ بررسی‌شدهٔ `src/utils/marketOnboarding.js`، کلید `localStorage` با نام `sokanex-market-confirmed:<user-id>` قبل از مقدار `market_selection_confirmed=false` بررسی می‌شود. این ترتیب باعث می‌شود کاربران قبلاً تأییدشده پس از reset دوباره فرم را نبینند. پیش از اجرای واقعی، فرانت باید در حالت `enabled=true` فقط مقدار تازهٔ بک‌اند را مرجع بداند؛ `confirmedFor` محلی در `MarketTypeOnboarding.jsx` هم نباید پاسخ false تازهٔ سرور را پنهان کند. تست فرانت باید حالتی را پوشش دهد که localStorage برابر true ولی پاسخ تازهٔ API برابر false است؛ فرم باید نمایش داده شود. برای کاربران فاقد نام، ابتدا مرحلهٔ تکمیل نام و سپس پرسش بازار نمایش داده شود. تا استقرار و آزمون این اصلاح، شرط «از همه دوباره پرسیده شود» محقق نیست.

## پیش‌نیاز و پیش‌نمایش

از snapshot سرور و backup قابل بازیابی دیتابیس/رسانه مطمئن شوید. پس از دریافت commit و پیش از اجرا، تست‌های زیر را با SQLite ایزوله اجرا کنید؛ روی PostgreSQL production تستی که دیتابیس تازه می‌سازد اجرا نکنید:

```bash
cd /srv/trading-platform/backend
pid=$(systemctl show -p MainPID --value trading-platform.service)
tr '\0' '\n' < "/proc/$pid/environ" | grep '^MARKET_ACCESS_V2_ENABLED=True$'
/srv/trading-platform/venv/bin/python manage.py check
/srv/trading-platform/venv/bin/python manage.py makemigrations --check --dry-run
DB_ENGINE=sqlite /srv/trading-platform/venv/bin/python manage.py test apps.accounts.test_reset_market_access_v2_baseline apps.accounts.test_market_access_requests apps.accounts.test_registration_market_journey
MARKET_ACCESS_V2_ENABLED=True /srv/trading-platform/venv/bin/python manage.py reset_market_access_v2_baseline
```

گزارش آخر باید `mode: dry_run` و `market_access_v2_enabled_in_this_process: true` باشد. به‌ویژه `normal_users`، `active_or_scheduled_v2_trials_to_revoke`، `v2_trial_history_retained` و `eligible_for_future_v2_trial_after_reset` را بررسی کنید. خروجی فقط شمارش دارد و شمارهٔ تلفن/نام کاربری را چاپ نمی‌کند. محیط `systemd` به shell روت به ارث نمی‌رسد؛ به همین دلیل flag برای اجرای command صریحاً در ابتدای همان خط گذاشته شده است.

## اجرای واقعی؛ فقط پس از تأیید سیاست Trial

اگر صاحب محصول تأیید کرد که Trialهای V2 فعلی مصرف‌شده باقی بمانند و backup موفق است، در پنجرهٔ استقرار این فرمان را **یک بار** اجرا کنید:

```bash
MARKET_ACCESS_V2_ENABLED=True /srv/trading-platform/venv/bin/python manage.py reset_market_access_v2_baseline --apply --confirm-trials-remain-used
```

فرمان atomic و audited است. اگر audit شکست بخورد، تمام تغییرات همان عملیات rollback می‌شود. اجرای دوباره باید `users_to_audit: 0` بدهد؛ فقط حساب‌هایی که در فاصلهٔ دو اجرا تغییر کرده باشند دوباره هدف می‌شوند. عملیات SMS گروهی ارسال نمی‌کند و سشن‌های کاربران را به‌طور گسترده باطل نمی‌کند.

## تأیید بعد از اجرا

```bash
MARKET_ACCESS_V2_ENABLED=True /srv/trading-platform/venv/bin/python manage.py reset_market_access_v2_baseline
MARKET_ACCESS_V2_ENABLED=True /srv/trading-platform/venv/bin/python manage.py audit_market_access_v2
/srv/trading-platform/venv/bin/python manage.py shell -c "from django.db.models import Q; from django.utils import timezone; from apps.accounts.models import User as U, UserAccessProfile as P, UserMarketGrant as G, TrialGrant as T; n=U.objects.exclude(Q(is_superuser=True)|Q(role__in=('SUPER_ADMIN','SUPPORT'))); print({'normal_levels_not_one':n.exclude(access_level=1).count(),'normal_confirmed':P.objects.filter(user__in=n,market_selection_confirmed_at__isnull=False).count(),'normal_active_grants':G.objects.filter(user__in=n,revoked_at__isnull=True).count(),'normal_unrevoked_trials':T.objects.filter(user__in=n,revoked_at__isnull=True,ends_at__gt=timezone.now()).count()})"
systemctl restart trading-platform.service
curl -fsS --max-time 10 http://127.0.0.1:8000/api/health/
```

در پیش‌نمایش دوم، `legacy_levels_to_one`، `active_v2_grants_to_revoke`، `active_or_scheduled_v2_trials_to_revoke` و `market_confirmations_to_reset` باید صفر باشند؛ چهار شمارش مستقیم بالا نیز باید صفر باشند. برای یک کاربر عادی، `GET /api/accounts/profile/market-preferences/` باید `membership_tier=LEVEL_1`، `market_selection_confirmed=false`، `trial_active=false` و `effective_markets=[]` برگرداند. پس از ثبت بازار، `market_selection_confirmed=true` باید با refresh باقی بماند. پاسخ dashboard نیز V2 را در `data.market_access_v2` دارد. JWT را در گزارش یا چت قرار ندهید.

این بازتنظیم خرید/کیف پول، roleهای مدیریتی و سوابق `UpgradeRequest` را دست‌کاری نمی‌کند. اگر بعداً gate V2 خاموش شود، `access_level` فیزیکی کاربران همچنان ۱ می‌ماند؛ بازگشت به وضعیت قبل مستلزم restore برنامه‌ریزی‌شده از backup است، نه صرفاً خاموش‌کردن flag.
