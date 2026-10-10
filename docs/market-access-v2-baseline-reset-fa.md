# بازتنظیم یک‌بارهٔ کاربران عادی به سطح ۱

این عملیات **جدا از migration** است. تا اجرای آگاهانهٔ `--apply`، هیچ حساب production تغییر نمی‌کند. فقط کاربران غیر `SUPER_ADMIN`، غیر `SUPPORT` و غیر `is_superuser` هدف هستند؛ نقش‌ها، درخواست‌ها، سوابق Trial و انتخاب‌های قبلی بازار حذف نمی‌شوند.

## نتیجهٔ عملیات

- مقدار واقعی `User.access_level` هر کاربر عادی ۱ می‌شود؛ این فیلد دیگر صرفاً نمای قدیمیِ سطح ۵ باقی نمی‌ماند.
- grantهای فعال V2 و Trialهای فعال/زمان‌بندی‌شدهٔ V2 لغو و Elite پاک می‌شود. `market_access_v2.membership_tier` سپس `LEVEL_1`، `trial_active=false` و `effective_markets=[]` است.
- `market_selection_confirmed_at` پاک می‌شود؛ حتی اگر انتخاب‌های پیشین برای پیش‌پرکردن فرم باقی بمانند، کاربر باید دوباره آن‌ها را با `PUT /api/accounts/profile/market-preferences/` تأیید کند. فرانت باید **فقط** `market_selection_confirmed` را برای نمایش فرم ملاک بگیرد، نه خالی/پر بودن `selected_markets` یا `market_type` قدیمی.
- سوابق `TrialGrant` V2 حذف نمی‌شوند؛ رکوردهای پیش از این بازتنظیم با `invalidated_at` علامت می‌خورند و دیگر سهمیهٔ یک‌بار Trial دورهٔ جدید را مصرف نمی‌کنند. بنابراین همهٔ کاربران عادیِ فعال پس از بازتنظیم، اگر grant بازار نداشته باشند، برای **یک کمپین جدید** واجد شرایط‌اند. Trial جدید پس از انقضا یا لغو همچنان مصرف‌شده می‌ماند و بار دوم داده نمی‌شود.
- خود بازتنظیم یک‌باره است و اجرای مجدد `--apply` خطا می‌دهد؛ بدین ترتیب کمپین جدید با اجرای دوباره ناخواسته لغو نمی‌شود. کمپین را فقط **پس از** بازتنظیم اجرا کنید. پیامک‌های معلق دورهٔ پیشین نیز نباید در دورهٔ تازه ارسال شوند.
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
DB_ENGINE=sqlite /srv/trading-platform/venv/bin/python manage.py test apps.accounts.test_reset_market_access_v2_baseline apps.accounts.test_market_access_requests apps.accounts.test_registration_market_journey apps.accounts.test_market_trial apps.accounts.test_market_access_v2 apps.notifications.test_sms_automation apps.wallet.test_premium_usd
MARKET_ACCESS_V2_ENABLED=True /srv/trading-platform/venv/bin/python manage.py reset_market_access_v2_baseline
```

گزارش آخر باید `mode: dry_run`، `already_applied: false` و `market_access_v2_enabled_in_this_process: true` باشد. به‌ویژه `normal_users`، `pre_reset_v2_trials_to_invalidate`، `v2_trial_history_retained` و `eligible_for_future_v2_trial_after_reset` را بررسی کنید. خروجی فقط شمارش دارد و شمارهٔ تلفن/نام کاربری را چاپ نمی‌کند. محیط `systemd` به shell روت به ارث نمی‌رسد؛ به همین دلیل flag برای اجرای command صریحاً در ابتدای همان خط گذاشته شده است.

## اجرای واقعی؛ پس از backup، migration و آزمون

ابتدا migration `accounts.0026_trial_reset_history` را اعمال و تست‌ها را اجرا کنید. بعد از اطمینان از backup موفق و اصلاح فرانت، در پنجرهٔ استقرار این فرمان را **یک بار** اجرا کنید:

```bash
MARKET_ACCESS_V2_ENABLED=True /srv/trading-platform/venv/bin/python manage.py reset_market_access_v2_baseline --apply --confirm-trial-history-voided
```

فرمان atomic و audited است. اگر audit شکست بخورد، تمام تغییرات همان عملیات rollback می‌شود. اجرای دوباره با خطای «already been applied» متوقف می‌شود و هیچ Trial تازه‌ای را تغییر نمی‌دهد. عملیات SMS گروهی ارسال نمی‌کند و سشن‌های کاربران را به‌طور گسترده باطل نمی‌کند.

## تأیید بعد از اجرا

```bash
MARKET_ACCESS_V2_ENABLED=True /srv/trading-platform/venv/bin/python manage.py reset_market_access_v2_baseline
MARKET_ACCESS_V2_ENABLED=True /srv/trading-platform/venv/bin/python manage.py audit_market_access_v2
/srv/trading-platform/venv/bin/python manage.py shell -c "from django.db.models import Q; from django.utils import timezone; from apps.accounts.models import User as U, UserAccessProfile as P, UserMarketGrant as G, TrialGrant as T; n=U.objects.exclude(Q(is_superuser=True)|Q(role__in=('SUPER_ADMIN','SUPPORT'))); print({'normal_levels_not_one':n.exclude(access_level=1).count(),'normal_confirmed':P.objects.filter(user__in=n,market_selection_confirmed_at__isnull=False).count(),'normal_active_grants':G.objects.filter(user__in=n,revoked_at__isnull=True).count(),'normal_current_trials':T.objects.filter(user__in=n,invalidated_at__isnull=True).count()})"
systemctl restart trading-platform.service
curl -fsS --max-time 10 http://127.0.0.1:8000/api/health/
```

در پیش‌نمایش دوم، `already_applied=true`، `legacy_levels_to_one`، `active_v2_grants_to_revoke`، `pre_reset_v2_trials_to_invalidate` و `market_confirmations_to_reset` باید صفر باشند؛ چهار شمارش مستقیم بالا نیز باید صفر باشند. برای یک کاربر عادی، `GET /api/accounts/profile/market-preferences/` باید `membership_tier=LEVEL_1`، `market_selection_confirmed=false`، `trial_used=false`، `trial_active=false` و `effective_markets=[]` برگرداند. پس از ثبت بازار، `market_selection_confirmed=true` باید با refresh باقی بماند. پاسخ dashboard نیز V2 را در `data.market_access_v2` دارد. JWT را در گزارش یا چت قرار ندهید.

این بازتنظیم خرید/کیف پول، roleهای مدیریتی و سوابق `UpgradeRequest` را دست‌کاری نمی‌کند. اگر بعداً gate V2 خاموش شود، `access_level` فیزیکی کاربران همچنان ۱ می‌ماند؛ بازگشت به وضعیت قبل مستلزم restore برنامه‌ریزی‌شده از backup است، نه صرفاً خاموش‌کردن flag.
