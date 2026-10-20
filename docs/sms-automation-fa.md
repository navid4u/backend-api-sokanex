# SMS Automation سوکانکس — قرارداد و استقرار

این قابلیت از همان تنظیمات `PAYAMITO_*` و کلاس `PayamitoSMSService` موجود استفاده می‌کند؛ هیچ API key از پاسخ‌های مدیریتی برنمی‌گردد. OTP و اعلان‌های قبلی تغییر نمی‌کنند. کلید ایمنی مستقل `SMS_AUTOMATION_ENABLED` پیش‌فرض `False` است و تمام ruleهای migration `notifications.0005_sms_automation` هم ابتدا **خاموش** هستند؛ استقرار کد به‌تنهایی پیامکی ارسال نمی‌کند.

## دسترسی و پاسخ‌ها

تمام مسیرها زیر `https://api.sokanex.com/api/notifications/sms-automation/` هستند و `Authorization: Bearer <access_token>` نیاز دارند. فقط `is_superuser` یا نقش واقعی `SUPER_ADMIN` مجاز است. `GET /api/dashboard/` برای همین کاربران `data.capabilities.can_manage_sms_automation=true` برمی‌گرداند. APIهای مدیریتی عموماً object یا DRF pagination استاندارد برمی‌گردانند؛ خطاها ممکن است در wrapper استاندارد پروژه باشند.

- `GET status/`: `automation_enabled`, `provider_configured`, `market_access_v2_enabled`, `enabled_rules`, `pending`, `needs_reconciliation`؛ فقط boolean، هرگز رمز یا کلید.
- `GET rules/`: آرایه ruleها. هر `slot` و `market` ثابت و منحصربه‌فرد است. slotهای پیش‌فرض: `WELCOME`, `ACCESS_CHANGE`, `TRIAL_1`, `TRIAL_3`, `TRIAL_5`, `TRIAL_6`, `TRIAL_7`؛ برای `ALL`, `internal`, `forex`, `crypto`.
- `GET/PATCH rules/{id}/`: `text`, `enabled`, و زمان‌بندی قابل ویرایش‌اند. `trial_day` فقط برای Trial و بین ۱ تا ۷ است؛ ساعت Trial در `send_time_utc` با فرم `HH:MM:SS` و timezone **UTC** تنظیم می‌شود. برای Welcome/Access Change، `delay_minutes` تأخیر بعد از رویداد است (۰ تا ۱۰۰۸۰؛ پیش‌فرض صفر). rule روشن مختص بازار بر rule روشن `ALL` اولویت دارد؛ بازار اصلی از بازارهای انتخابی V2 تعیین می‌شود (اگر `market_type` قدیمی در انتخاب‌ها باشد اولویت دارد، وگرنه نخستین بازار الفبایی؛ در نبود انتخاب V2 از `market_type` استفاده می‌شود). برای چند بازار، در این نسخه یک پیامک برای هر رویداد فرستاده می‌شود.
- متغیرهای متن فقط `{first_name}`, `{last_name}`, `{days_remaining}`, `{support_link}`, `{membership_tier}`, `{market_name}` هستند. متن نهایی حداکثر ۵۰۰ کاراکتر؛ HTML و دسترسی نقطه‌ای/format spec ممنوع. لینک پشتیبانی از env `SMS_AUTOMATION_SUPPORT_LINK` (پیش‌فرض `https://app.sokanex.com/support`) می‌آید.
- `GET deliveries/?page=1&page_size=20&status=SENT&event=TRIAL&user_id=123&search=...&ordering=-sent_at`: `count,next,previous,results`؛ ترتیب‌های مجاز `created_at`, `-created_at`, `sent_at`, `-sent_at` هستند. هر سطر علاوه بر فیلدهای قبلی، `rendered_text` (snapshot متن) و `error_code` (در نبود خطا `null`) دارد. هر پنج وضعیت `PENDING|SENDING|SENT|FAILED|SKIPPED` در گزارش بدون فیلتر قابل مشاهده‌اند. `SENDING` قدیمی ممکن است «ارسال شده ولی ثبت نتیجه نشده» باشد؛ خودکار تکرار نمی‌شود تا پیام تکراری نرود.
- `GET broadcasts/`: تاریخچهٔ ارسال‌های گروهی.

## ارسال گروهی با تأیید دو مرحله‌ای

برای هر بار ارسال، اول `POST broadcasts/preview/`:

```json
{"membership_tiers":["LEVEL_1","BASIC"],"market":"forex","text":"{first_name} عزیز، خبر جدید سوکانکس: {support_link}"}
```

پاسخ شامل `eligible_count` و `candidate_digest` است. tierها سطح **محاسبه‌شدهٔ Market Access V2** هستند: صفر بازار تأییدشده `LEVEL_1`، یک بازار `BASIC`، دو بازار `PRO` و سه بازار `GOLD`. `ELITE` یک نشان مستقل (`is_elite`) است؛ انتخاب هم‌زمان سطح پایه و `ELITE` اجتماع بدون تکرار مخاطبان است. Trial دسترسی موقت به محتوا می‌دهد ولی tier پایه را عوض نمی‌کند. بازار `ALL` هیچ فیلتر بازاری اعمال نمی‌کند؛ بازار مشخص با **انتخاب‌های کاربر** (`selected_markets`) مقایسه می‌شود، نه بازارهای تأییدشده یا `market_type` قدیمی. فقط کاربر فعال، غیرسوپرادمین/پشتیبان و دارای موبایل معتبر وارد پیش‌نمایش می‌شود؛ نقش `ADMIN` اگر سطح پایه و سایر شرایط را داشته باشد، مستثنا نیست.

فیلد افزایشی `diagnostics` فقط در همین پاسخ مدیریتی قرار دارد: `matched_count` تعداد کاربران عادی منطبق با tier و بازار **پیش از شرایط ارسال** است و `excluded_counts` تعداد حذف‌شده‌ها را به ترتیب انحصاری `inactive`، `missing_phone` و `invalid_phone` نشان می‌دهد. همواره `matched_count = eligible_count +` مجموع این حذف‌ها است. این شمارش‌ها هیچ شماره، شناسهٔ مخاطب یا اطلاعات provider را افشا نمی‌کنند. preview و send همان تابع انتخاب مخاطب را استفاده می‌کنند و digest همچنان از snapshot واقعی مخاطبان ساخته می‌شود.

پس از نمایش تعداد واقعی و تأیید صریح مدیر، `POST broadcasts/send/` با همان بدنه و این چهار مقدار:

```json
{"expected_eligible_count":42,"expected_candidate_digest":"<sha256-from-preview>","idempotency_key":"uuid-or-random-stable-key","confirm":true}
```

اگر تعداد/مخاطبان/متن تغییر کند 409 `AUDIENCE_CHANGED` و هیچ صفی ساخته نمی‌شود. ارسال موفق 201 با `id,status=QUEUED,recipient_count`؛ تکرار با همان idempotency key و همان payload پاسخ 200 و همان id می‌دهد. همان کلید برای payload دیگر 409 است. هر مخاطب یک snapshot مستقل از شماره و متن دارد. پاسخ HTTP به معنی تحویل توسط اپراتور نیست؛ `deliveries/` را بررسی کنید.

## زمان‌بندی و توقف Trial

روز ۱ Journey برای Trial جدیدِ ثبت‌نام‌شده، پس از commit همان نشست در صف ثبت می‌شود؛ worker پنج‌دقیقه‌ای مسیر بازیابی است. در مسیر Rule قدیمی نیز ساعت `send_time_utc` واقعاً UTC است و برای هر کاربر بر مبنای زمان شروع خودش محاسبه می‌شود. `TRIAL_7`/متن پایان دوره هرگز زودتر از `trial_ends_at` صف یا ارسال نمی‌شود. اگر Journey فعال است، Ruleهای قدیمی Trial غیرفعال‌اند و Journey مالک روز اول/خوشامد کاربرِ enrolled است؛ رخداد WELCOME مستقل برای همان کاربر با علت `JOURNEY_OWNS_WELCOME` به‌صورت SKIPPED ثبت می‌شود. WELCOME فعال برای ثبت‌نام جدیدِ بدون enrollment همچنان مستقل کار می‌کند. بازکردن دوبارهٔ Rule قدیمی Trial هنگام Journey مجاز نیست. در هر نوبت، اگر کاربر grant دائمی بازار گرفته یا Trial لغو شده باشد، پیام‌های Trial آینده ساخته نمی‌شوند و پیام‌های pending مربوطه `SKIPPED` می‌شوند. ورود یا تغییر سطح رسمی از audit دسترسی‌های V2 می‌آید؛ تغییر roleهای مدیریتی یا فیلد legacy `access_level` سناریوی V2 را فعال نمی‌کند. Welcome فقط پس از ساخت نشست موفق ثبت‌نام جدید صف می‌شود؛ ساخت خام User یا ثبت‌نام ناموفق پیام ندارد.

## استقرار امن

1. بکاپ عادی دیتابیس و snapshot را جداگانه تأیید کنید. سپس `git fetch` / `git merge --ff-only` نسخهٔ جدید، `python manage.py check`, `python manage.py makemigrations --check --dry-run`, `python manage.py migrate --plan`, `python manage.py migrate` را در `/srv/trading-platform/backend` اجرا کنید.
2. قبل از نصب timer، با `systemctl cat trading-platform.service` فایل/محل واقعی environment سرویس Gunicorn را ببینید. فایل `deployment/systemd/sokanex-sms-automation.service` نمونه است و `EnvironmentFile` آن **باید** به همان env امن سرویس شما اشاره کند؛ وجود `.env` در مسیر نمونه فرض قطعی نیست. کلید را چاپ نکنید. `SMS_AUTOMATION_SUPPORT_LINK` را هم در همان env تنظیم کنید. `SMS_AUTOMATION_ENABLED=True` باید هم در Gunicorn و هم در worker تعریف شده باشد؛ تا آن زمان همه‌چیز خاموش است.
3. `install -m 0644 deployment/systemd/sokanex-sms-automation.{service,timer} /etc/systemd/system/` در بعضی shellها glob brace را درست گسترش نمی‌دهد؛ هر فایل را جدا نصب کنید. سپس `systemctl daemon-reload` و ابتدا یک نوبت `systemctl start sokanex-sms-automation.service` را با **همه ruleها خاموش** اجرا کنید. `systemctl show ... -p Result -p ExecMainStatus` و `journalctl -u ... --no-pager -n 30` را بررسی کنید.
4. فقط پس از تست Rule و شمارش مخاطبان، `systemctl enable --now sokanex-sms-automation.timer` کنید. `systemctl list-timers --all | grep sokanex-sms-automation` باید نوبت بعد را نشان دهد. worker مستقل از Gunicorn است.
5. هنگام فعال‌کردن Rule یا ساخت Broadcast، هزینهٔ واقعی پیامک با ظرفیت پنل پیامیتو را لحاظ کنید. ابتدا با یک مخاطب تستی کم‌خطر آزمایش کنید. وضعیت `provider_configured` و لاگ تحویل را چک کنید.

در rollback رفتاری، `SMS_AUTOMATION_ENABLED=False` را در هر دو سرویس تنظیم کنید و timer را `disable --now` کنید؛ این کار OTP را خاموش نمی‌کند. migration را برای rollback معمولی معکوس نکنید، چون تاریخچهٔ پیامک حذف می‌شود. برای رکورد `SENDING` مانده، قبل از هر تکرار با اپراتور تطبیق دهید. هیچ retry خودکار برای پاسخ‌های مبهم provider انجام نمی‌شود.
