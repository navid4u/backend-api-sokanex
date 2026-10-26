# آپلود تکه‌ای ویدئوی جلسهٔ آکادمی

این تغییر افزایشی است. `POST /api/academy/courses/{slug}/sessions/` برای فایل‌های کوچک باقی می‌ماند. برای فایل بزرگ، فرانت نباید ویدئوی کامل را به آن endpoint بفرستد؛ پاسخ `402` HTML از WCDN برای بدنهٔ بزرگ قبل از رسیدن به Gunicorn رخ داده است. این کد سقف WCDN را تغییر نمی‌دهد، بلکه هر درخواست را زیر آن نگه می‌دارد.

## قرارداد فرانت

تمام درخواست‌ها با همان Bearer JWT و روی `https://api.sokanex.com` هستند. مجوز تدریس/مدیریت دوره در تمام گام‌ها روی سرور بررسی می‌شود. `slug` در URL باید `encodeURIComponent` شود.

1. یک UUID v4 تصادفی برای `client_upload_id` بسازید و تا پایان کار همراه فایل در وضعیت فرانت نگه دارید. `POST /api/academy/courses/{slug}/session-video-uploads/` با JSON:

   ```json
   {"filename":"lesson.mp4","size":186606847,"client_upload_id":"UUID-V4"}
   ```

   `sha256` هگز ۶۴ کاراکتری اختیاری است؛ برای فایل بزرگ مجبور به خواندن کل فایل در حافظهٔ مرورگر نشوید. پاسخ ۲۰۱ حاوی `upload_id`, `offset=0`, `size`, `chunk_size=4194304`, `expires_at` است. تکرار همین شروع با همان `client_upload_id` و فایل یکسان، ۲۰۰ و همان آپلود را می‌دهد؛ استفاده از شناسه برای فایل دیگر ۴۰۹ است.

2. فایل را به ترتیب و هر بار حداکثر `chunk_size` برش دهید. هر قطعه جز آخر باید دقیقاً `chunk_size` باشد. `PUT /api/academy/courses/{slug}/session-video-uploads/{upload_id}/chunk/` با `Content-Type: application/octet-stream`، هدر `X-Upload-Offset: <offset>` و بدنهٔ خام `file.slice(offset, offset + chunk_size)` ارسال شود. `FormData` و JSON برای قطعه نگذارید. پاسخ ۲۰۰ `offset` جدید می‌دهد. پس از خطای شبکه، ابتدا `GET /api/academy/courses/{slug}/session-video-uploads/{upload_id}/` را بخوانید و از `offset` واقعی سرور ادامه دهید؛ قطعهٔ یکسان در offset قبلی قابل Retry و بی‌اثر است. قطعهٔ متفاوت یا offset نادرست ۴۰۹ می‌دهد. حداکثر دو آپلود فعال هم‌زمان برای هر کاربر و مهلت هر آپلود ۲۴ ساعت است.

3. پس از رسیدن `offset` به `size`، `POST /api/academy/courses/{slug}/session-video-uploads/{upload_id}/complete/` را با فرادادهٔ همان فرم جلسه بفرستید: `title`, `order`, `duration_minutes`, `text`, `is_published`, `is_preview`, `video_url: ""` و تصویر اختیاری. برای تصویر، multipart کوچک مجاز است؛ ویدئو را دوباره در این درخواست نگذارید. پاسخ ۲۰۱ همان آبجکت `CourseSessionSerializer` قدیمی است. Retry مرحلهٔ نهایی پاسخ ۲۰۰ همان جلسه را می‌دهد؛ سپس لیست جلسات را دوباره بخوانید. اگر validation ۴۰۰ شد، فراداده را اصلاح کنید و دوباره complete را بزنید؛ آپلود ویدئو باقی می‌ماند.

4. انصراف: `DELETE /api/academy/courses/{slug}/session-video-uploads/{upload_id}/` پاسخ ۲۰۴ می‌دهد. برای فایل کوچک می‌توانید مسیر POST قبلی را نگه دارید. برای همهٔ ویدئوها نیز می‌توانید مسیر تکه‌ای را به‌کار ببرید. هنگام آپلود، پیشرفت را از `offset/size` نشان دهید، نه صرفاً ارسال HTTP؛ در قطع/رفرش صفحه با `client_upload_id` و GET وضعیت resume کنید. پس از انقضای ۲۴ساعته، آپلود تازه بسازید.

کدهای مهم: ۴۰۰ فرمت فایل/اعتبارسنجی/قطعهٔ نامعتبر؛ ۴۰۳ نداشتن مجوز؛ ۴۰۴ دوره یا آپلود متعلق به فرد دیگر؛ ۴۰۹ تداخل offset، هش یا وضعیت؛ ۴۱۰ انقضا. خطاهای HTTP را «Network Error» عمومی نمایش ندهید؛ متن و `code` پاسخ JSON را نشان دهید. درخواست PUT با هدر `X-Upload-Offset` باعث preflight CORS می‌شود و این هدر در backend مجاز شده است.

## استقرار production، با SSH و بکاپ

قبل از تغییر، مطمئن شوید `git status --short` تغییرات ناخواستهٔ سرور را نشان نمی‌دهد. پوشهٔ خصوصی نباید زیر `/media/` یا وب‌روت باشد:

```bash
cd /srv/trading-platform/backend
systemctl start trading-platform-backup.service
systemctl show trading-platform-backup.service -p Result -p ExecMainStatus --no-pager
git fetch origin backend-with-frontedits
git merge --ff-only origin/backend-with-frontedits
install -d -o tradingapp -g tradingapp -m 0700 /srv/trading-platform/private-academy-uploads
/srv/trading-platform/venv/bin/python manage.py check
/srv/trading-platform/venv/bin/python manage.py makemigrations --check --dry-run
/srv/trading-platform/venv/bin/python manage.py migrate --plan
/srv/trading-platform/venv/bin/python manage.py migrate --noinput
/srv/trading-platform/venv/bin/python manage.py migrate --check
systemctl restart trading-platform.service
sleep 5
curl -fsS --max-time 15 http://127.0.0.1:8000/api/health/
```

تنظیم پیش‌فرض مسیر خصوصی `/srv/trading-platform/private-academy-uploads` است. اگر `ACADEMY_UPLOAD_STAGING_ROOT` را در `.env` تغییر داده‌اید، همان مسیر را با مالک `tradingapp` و مجوز `0700` بسازید. این مسیر روی یک فایل‌سیستم مشترک بین همهٔ workerهای Gunicorn باشد و برای ویدئوی ۵۰۰ مگابایتی فضای آزاد کافی داشته باشد. درخواست‌های قدیمی به migration جدید وابسته نیستند، ولی endpointهای تکه‌ای قبل از migration نباید استفاده شوند.

پاک‌سازی فایل‌های موقت منقضی‌شده:

```bash
install -m 0644 deployment/systemd/sokanex-academy-upload-cleanup.service /etc/systemd/system/
install -m 0644 deployment/systemd/sokanex-academy-upload-cleanup.timer /etc/systemd/system/
systemctl daemon-reload
systemctl start sokanex-academy-upload-cleanup.service
systemctl show sokanex-academy-upload-cleanup.service -p Result -p ExecMainStatus --no-pager
systemctl enable --now sokanex-academy-upload-cleanup.timer
systemctl is-active sokanex-academy-upload-cleanup.timer
```

اول backend را استقرار دهید و health و OPTIONS را بررسی کنید. سپس نسخهٔ جدید فرانت را آپلود کنید. تست واقعی: با حساب مجاز، یک فایل کوچکِ واقعی از مسیر جدید آپلود، GET جلسه و پخش ویدئو را بررسی کنید؛ بعد فایل ۱۳۰ مگابایتی را امتحان کنید. `HTTP 200` health یا قبولی تست محلی، اثبات عبور قطعه‌ها از WCDN و ذخیرهٔ نهایی در production نیست. با همان ۱۳۰MB، در Network باید چندین `PUT` کوچک و یک `POST complete` ببینید؛ هیچ POST با بدنهٔ ۱۸۶MB نباید ارسال شود.

اگر هر قطعهٔ ۴MiB نیز پیش از Gunicorn رد شد، سقف واقعی WCDN کمتر از این مقدار است؛ باید chunk_size سرور و فرانت را با هم پایین آورد (مثلاً ۱MiB)، نه اینکه درخواست کامل دوباره ارسال شود. بدون دسترسی به CDN، کد backend نمی‌تواند محدودیت بدنهٔ همان CDN را حذف کند.
