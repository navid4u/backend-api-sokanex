# پرامپت آماده برای پیاده‌سازی فرانت Market Access V2 سوکانکس

در پروژهٔ React/Vite سوکانکس، ساختار فعلی را حفظ و UI دسترسی کاربران را با Backend جدید هماهنگ کن. پیش از ویرایش، checkout فعلی frontend را بررسی کن و فرض نکن snapshot قدیمی آخرین نسخه است. Backend endpointهای قبلی را نگه داشته، اما V2 با `MARKET_ACCESS_V2_ENABLED` مرحله‌ای فعال می‌شود. تغییرات فرانت باید additive، responsive، فارسی/RTL، دارای loading/empty/error state و تست باشد. از ساختن level یا مجوز محلی خودداری کن.

## منبع حقیقت و سازگاری انتشار

- `GET /api/dashboard/` پاسخ wrapper استاندارد `success/data` دارد؛ `data.market_access_v2` و `data.capabilities.can_manage_market_access` را بخوان.
- `GET /api/accounts/profile/details/` object مستقیم برمی‌گرداند و `market_access_v2` را نیز دارد. بعضی APIهای دیگر ممکن است wrapper داشته باشند؛ helper موجود پروژه را حفظ کن.
- `market_access_v2.enabled === false` یعنی V2 هنوز فعال نیست: UI جدید، درخواست‌های V2 و اجبار onboarding را نشان نده؛ رفتار legacy حفظ شود. 403 مسیر V2 هنگام خاموش‌بودن flag را خطای login تلقی نکن.
- فقط وقتی `enabled === true` است UI جدید را نشان بده و درخواست‌های legacy Trial/Gold/purchase/upgrade را برای این مسیر **هرگز** صدا نزن. ابتدا فرانت را با حالت خاموش deploy کن، بعد از smoke test بک‌اند و هماهنگی deployment، flag را روشن کن.
- فیلد قدیمی `access_level` و `premium_subscription` برای سازگاری باقی مانده‌اند؛ در حالت V2 آن‌ها را معیار Tier، Trial یا دسترسی قرار نده. `market_type` قدیمی فقط ترجیح تک‌بازاری/شخصی‌سازی است و نباید جای سه checkbox V2 یا grant واقعی استفاده شود.
- از `membership_tier`، `selected_markets`، `approved_markets`، `effective_markets`، `market_selection_confirmed`، `trial_used`، `trial_active`، `trial_started_at`، `trial_ends_at`، `is_elite`، `has_gold_features` و `special_role` مستقیماً از بک‌اند استفاده کن. بعد از هر PUT/POST/PATCH موفق، dashboard/profile را refresh کن؛ دسترسی را خوش‌بینانه یا در localStorage تغییر نده.

نمونهٔ `market_access_v2` برای کاربر عادی:

```json
{
  "enabled": true,
  "membership_tier": "PRO",
  "selected_markets": ["crypto", "forex"],
  "approved_markets": ["crypto", "forex"],
  "effective_markets": ["crypto", "forex"],
  "market_selection_confirmed": true,
  "trial_used": false,
  "trial_active": false,
  "trial_started_at": null,
  "trial_ends_at": null,
  "is_elite": false,
  "has_gold_features": false,
  "special_role": null
}
```

صفر grant = `LEVEL_1`، یک grant = `BASIC`، دو grant = `PRO`، سه grant = `GOLD`. `ELITE` یک نشان مستقل است و جایگزین Tier نیست. Trial فعال، `effective_markets` را موقتاً به هر سه بازار و `has_gold_features` را true می‌رساند، اما `membership_tier` اصلی را عوض نمی‌کند. انقضا با زمان سرور در API مشخص می‌شود؛ شمارش معکوس فرانت فقط نمایشی باشد و هنگام focus/refresh دوباره از بک‌اند بخواند. Superadmin و Support با `special_role` از سطح‌بندی معمول کاربران جدا هستند؛ دسترسی قبلی پنل‌هایشان حفظ شود.

## API client و onboarding

در `src/api/accounts.api.js` توابع زیر را به client موجودِ JWT Bearer اضافه کن؛ base URL را hard-code یا token را log نکن:

- `GET/PUT /api/accounts/profile/market-preferences/`؛ body PUT دقیقاً `{ "selected_markets": ["internal", "forex", "crypto"] }` با هر زیرمجموعهٔ یکتا. پاسخ object مستقیم `market_access_v2` است. این انتخاب **مجوز دسترسی نمی‌دهد** و فقط ثبت درخواست/علاقه است.
- `GET/POST /api/accounts/market-access/requests/`؛ body POST `{ "requested_tier": "PRO"|"GOLD"|"ELITE", "message": "" }`. بک‌اند `requested_markets` را از انتخاب ثبت‌شده می‌گیرد؛ آن را در body جعل نکن. درخواست تازه 201، تکرار همان PENDING برابر 200، تعارض 409 است. Pro به دست‌کم دو بازار انتخاب‌شده و Gold به هر سه بازار نیاز دارد؛ حتی با validation فرانت، پاسخ 400/409 بک‌اند را دقیق نمایش بده.

وقتی `enabled=true` و `market_selection_confirmed=false` است، پس از login/onboarding برای کاربر عادی یک modal سه‌چک‌باکسی «بازار داخلی / فارکس / کریپتو» نشان بده. همین انتخاب در Profile و Settings همیشه قابل ویرایش باشد. تغییر checkbox فقط `selected_markets` را تغییر می‌دهد؛ `approved_markets` و Tier تا تأیید مدیر ثابت می‌مانند. وضعیت خالی را به‌صورت «هنوز بازاری تأیید نشده» نشان بده. برای Superadmin/Support این modal را اجرا نکن.

## صفحهٔ عضویت/درخواست کاربر

در `src/pages/UpgradePage.jsx` و `src/components/PremiumSubscriptionPanel.jsx`، وقتی V2 فعال است جریان قدیمی «فعال‌سازی Trial هفت‌روزه»، «خرید با کیف پول»، `premium/request/` و متن «Gold دائمی = سطح ۵» را پنهان/جایگزین کن؛ حذف API client یا کد legacy لازم نیست، چون حالت flag خاموش باید سالم بماند. در V2:

- Tier فعلی، بازارهای انتخاب‌شده و تأییدشده، نشان Elite، وضعیت Trial و پایان آن را از سرور نشان بده.
- امکان ثبت درخواست Pro/Gold/Elite را مطابق انتخاب‌ها بده. Basic از طریق grant مدیریتی یک بازار حاصل می‌شود؛ endpoint درخواست Basic وجود ندارد، پس دکمهٔ ساختگی آن نساز.
- تاریخچهٔ درخواست‌ها را از `GET /api/accounts/market-access/requests/` (pagination استاندارد DRF) بخوان؛ وضعیت `PENDING/APPROVED/REJECTED`، `admin_note` و `tier_description` را نشان بده. درخواست pending یکسان را دوباره نساز؛ خطای 409 را با پیام مناسب نمایش بده.
- هیچ قیمت، موجودی کیف پول، plan_id، idempotency مالی یا پرداخت را در این جریان V2 وارد نکن.

## مدیریت دسترسی‌ها و کاربران

در کنار مدیریت کاربران فعلی یک بخش مستقل «مدیریت دسترسی‌ها و کاربران» بساز؛ مدیریت نقش و سطح legacy را در UI V2 به‌عنوان کنترل Tier جدید استفاده نکن. APIها:

- `GET /api/accounts/admin/market-access/users/?page=1&search=...` با pagination استاندارد؛ هر ردیف `id, username, first_name, last_name, phone, role, is_active, date_joined, legacy_access_level, access` دارد.
- `GET/PATCH /api/accounts/admin/market-access/users/{id}/`؛ PATCH `{ "approved_markets": ["internal", "forex"], "is_elite": true }`؛ هر فیلد اختیاری است، ولی body خالی نامعتبر است. بعد از پاسخ، `access` جدید را بخوان. Level را جداگانه POST/PATCH نکن؛ بک‌اند از تعداد grantهای فعال محاسبه می‌کند. تغییر از دو بازار به سه بازار Pro→Gold و بالعکس را در UI نمایش بده. Superadmin/Support هدف ویرایش عادی نیستند.
- `GET/PATCH /api/accounts/admin/market-access/content-policy/`؛ GET سه ردیف `ARTICLES`, `VIDEOS`, `LIVESTREAMS` با `allowed_tiers` و `updated_at` می‌دهد. PATCH فقط `{ "section": "ARTICLES", "allowed_tiers": ["LEVEL_1", "BASIC", "PRO", "GOLD"] }`. پیش‌فرض هر چهار Tier باز است؛ خالی‌کردن آرایه عمداً یک بخش را برای کاربران عادی می‌بندد. این کنترل فقط در همین بخش مدیریت باشد. Checkboxهای `allowed_levels` قدیمی در فرم ایجاد/ویرایش مقاله، ویدئو و لایو در حالت V2 نمایش داده نشوند و payload قدیمی را ناخواسته پاک نکنند. شرط مستقل انتشار، خرید یا مالکیت همچنان برقرار است.

`data.capabilities.can_manage_market_access` معیار نمایش لینک این بخش است؛ اما Backend مجوز نهایی را enforce می‌کند. در `src/auth/AuthProvider.jsx` و `RoleGuard` دقت کن نقش SUPPORT امروز به‌طور کلی از `can(...)` کنار گذاشته شده است؛ برای **فقط همین capability جدید** استثنای کنترل‌شده بگذار تا Support بتواند این بخش را ببیند، بدون بازکردن بقیهٔ پنل‌ها. Superadmin نیز مجاز است. نقش‌ها و permissionهای legacy را تغییر نده.

## مدیریت درخواست‌ها

بخش مستقلی کنار مدیریت دسترسی‌ها اضافه کن؛ صفحهٔ قدیمی `UpgradeManagementPage.jsx` برای درخواست‌های PREMIUM legacy در حالت flag خاموش باقی بماند، اما در V2 جایگزین درخواست‌های جدید شود:

- `GET /api/accounts/admin/market-access/requests/?status=PENDING&search=...&page=1` با pagination DRF. هر ردیف شامل user با `first_name`, `last_name`, `username`, `phone`، بازارهای درخواستی، `requested_tier`، `tier_description`، پیام، status و یادداشت مدیر است.
- `PATCH /api/accounts/admin/market-access/requests/{id}/review/` برای تأیید، مثلاً `{ "status": "APPROVED", "approved_markets": ["internal", "forex"], "is_elite": false, "admin_note": "" }`. `approved_markets` باید غیرخالی و زیرمجموعهٔ انتخاب‌های فعلی کاربر باشد. برای Elite باید `is_elite=true` را آگاهانه ارسال کرد؛ Elite از تعداد بازارها مستقل است. Tier نهایی از **بازارهای تأییدشده** محاسبه می‌شود، نه عنوان درخواست.
- برای رد: `{ "status": "REJECTED", "admin_note": "علت رد" }` و هیچ فیلد تغییر access نفرست. اگر کاربر انتخاب بازارش را بعد از درخواست تغییر داده یا درخواست قبلاً بررسی شده، 409 را واضح نشان بده؛ refresh کن و با حدس وضعیت را تغییر نده.
- توضیح کوتاه Basic/Pro/Gold/Elite و بازارهای انتخابی/تأییدی را کنار تصمیم مدیر نشان بده تا تأیید اشتباه رخ ندهد.

## Trial فقط با دستور Superadmin

هیچ کاربر عادی دکمهٔ «شروع Trial» نداشته باشد. فقط Superadmin واقعی (یا is_superuser طبق بک‌اند) در پنل مدیریت:

1. `POST /api/accounts/admin/market-access/trial-campaigns/preview/` با `{}` برای همهٔ Level 1های واجد شرایط یا `{ "registered_from": "YYYY-MM-DD" }` برای کاربران ثبت‌نام‌شده از تاریخ مشخص. اگر UI شمسی است، قبل از ارسال آن را به Gregorian ISO تبدیل کن.
2. `eligible_count`, `duration_days`, `candidate_digest` و cohort را در مرحلهٔ تأیید واضح نشان بده. هیچ فهرست PII از preview انتظار نداشته باش.
3. فقط بعد از تأیید صریح مدیر، `POST /api/accounts/admin/market-access/trial-campaigns/` با `{ "registered_from": null, "expected_eligible_count": N, "expected_candidate_digest": "...", "confirm": true }`. برای cohort تاریخ‌دار همان تاریخ preview را بفرست. اگر preview stale شد، 409 را نشان بده و preview دوباره بگیر؛ اجرای خودکار یا retry کور ممنوع.
4. پاسخ 201 شامل `granted_count`, `started_at`, `ends_at` و `status=APPLIED` است. Trial یک‌بار در عمر حساب است؛ تکرار یا تمدید از فرانت طراحی نکن. Trial دادهٔ Gold/Wallet قدیمی را دست‌کاری نمی‌کند.

## نمایش محتوا و دسترسی

- در حالت V2، مقاله/ویدئو/لایو برای همهٔ Tierها پیش‌فرض بازند، مگر policy مدیریتی همان بخش آن Tier را بسته باشد. مدیریت سطح در خود فرم انتشار محتوا نباشد.
- آکادمی، دستیار مالی و اعلان عمومی از Basic به بالا؛ سیگنال VIP و تحلیل داخلی فقط با `has_gold_features=true` و دسترسی بازار مربوط. اعلان شخصیِ مستقیم، وضعیت انتشار محتوا، مالکیت، خرید، auth و محدودیت‌های امنیتی مستقل را حفظ کن.
- برای مخفی/نمایش اولیهٔ UI از state سرور استفاده کن، اما 403 واقعی API را هم هندل کن. در حالت عدم دسترسی، CTA مناسب انتخاب بازار/درخواست بده؛ spinner بی‌پایان یا صفحهٔ سیاه نباشد.
- `special_role=SUPER_ADMIN|SUPPORT` را مثل Level 1 عادی رندر نکن؛ پنل‌های فعلی نقش‌ها باقی بمانند.

## تست و تحویل

تست React/Vitest برای حالت flag خاموش و روشن، modal اولین انتخاب، ویرایش چندبازاری بدون افزایش access، Tierهای 0/1/2/3 بازار، Trial فعال/منقضی و فقط مدیریتی، Elite مستقل، Support و Superadmin، درخواست تکراری 200، خطاهای 400/403/409، مدیریت policy، pagination/search و نبود فراخوانی endpointهای پرداخت/Trial شخصی در V2 اضافه کن. تست رگرسیون login/OTP، profile، dashboard، سیگنال و PWA انجام بده. `npm.cmd run build` و تست‌ها را اجرا کن؛ خروجی واقعی frontend از `dist2` deploy می‌شود: پیش از انتشار مطمئن شو هر JS/CSS اشاره‌شده در `dist2/index.html` واقعاً در `dist2/assets` موجود است. هنگام فعال‌سازی V2 روی production، API authenticated را با کاربر عادی، مدیر، Support و Superadmin واقعاً تست کن؛ HTTP 200 یا build به‌تنهایی اثبات جریان کامل نیست.

در پایان فایل‌های تغییرکرده، تست‌های موفق، پاسخ‌های واقعی API، چیزهای deployشده و چیزهای هنوز deployنشده را دقیق گزارش کن. فرانت را قبل از هماهنگی روشن‌شدن feature flag منتشر کن، اما UI جدید فقط با `enabled=true` فعال شود.
