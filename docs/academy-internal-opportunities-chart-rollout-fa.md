# انتشار هماهنگی آکادمی، فرصت داخلی و نمودار داشبورد

- نسخهٔ آکادمی بدون فروش در commit `583aef9` قبلاً روی production گزارش شده است. این انتشار قرارداد JWT، مجوز بازار، خریدهای تاریخی و آپلود قطعه‌ای را تغییر نمی‌دهد.
- `content_channels.0006` فقط فیلدهای nullable فرصت و یک قید اعتبار قیمت اضافه می‌کند؛ دادهٔ تاریخی را پر یا تبدیل نمی‌کند.
- `GET /api/channels/internal-analysis/` فیلتر اختیاری `opportunity_status` دارد. `GET /api/channels/posts/{id}/` برای تحلیل داخلیِ منتشرشده با مجوز واقعی کاربر جزئیات همان serializer را می‌دهد؛ پست خصوصی یا بازار غیرمجاز 403 است. مدیریت می‌تواند فیلدها را روی endpointهای `/manage/` بنویسد.
- قیمت‌ها رشتهٔ decimal با هشت رقم اعشار یا null هستند؛ `views_count` شمارندهٔ موجود دیتابیس است. `entry_warning` فقط متن ثبت‌شده است.
- ۲۰ نماد در allowlist نمودار هستند. HYPE به CoinGecko `hyperliquid` و UKOIL به Twelve Data `XBR/USD` نگاشت می‌شود. این نگاشت، دسترس‌پذیری provider یا اعتبار اشتراک API را اثبات نمی‌کند.

## انتشار محافظه‌کارانه

پیش از تغییر schema بکاپ بگیرید، `git merge --ff-only` و `manage.py check` و `migrate --plan` را اجرا کنید. سپس migration را اعمال کنید. قبل از restart سرویس، با همان محیط server این دو probe فقط‌خواندنی را اجرا کنید:

```bash
/srv/trading-platform/venv/bin/python manage.py probe_dashboard_chart_symbols --range 1d
/srv/trading-platform/venv/bin/python manage.py probe_dashboard_chart_symbols --range 5d
```

هر خروجی باید `passed=20` و `total=20` داشته باشد. اگر شکست خورد، نتیجهٔ هر نماد را ببینید؛ 503 برای provider بدون تاریخچه، پاسخ درست است و نباید با عدد ساختگی جایگزین شود. فرمان probe قیمت و credential چاپ نمی‌کند. پس از تأیید، سرویس را restart کنید و درخواست احراز هویت‌شدهٔ فهرست، جزئیات، فیلتر و نمودار را تست کنید. دادهٔ production برای ساخت نمونهٔ فرصت تغییر ندهید.

نمونهٔ shape مورد انتظار از fixture آزمون (نه دادهٔ production):

```json
{"count":1,"next":null,"previous":null,"results":[{"id":1,"opportunity_status":"ACTIVE","direction":"BUY","entry_price_min":"25000000.00000000","entry_price_max":"25550000.00000000","take_profit":"28500000.00000000","stop_loss":"23400000.00000000","currency_label":"تومان","entry_warning":"Only stored warning","views_count":0}]}
```

جزئیات همان فیلدها و مقادیر را برمی‌گرداند؛ همراه با سایر فیلدهای موجود پست. شمارندهٔ صفر در نمونه صرفاً مقدار واقعی fixture تازه‌ساخته است.
