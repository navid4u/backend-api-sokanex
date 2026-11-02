# مقایسهٔ پلتفرم‌ها و دسترسی آکادمی — راهنمای انتشار

## قرارداد بک‌اند

- ریشهٔ جدید مستقل از brokers قدیمی: `/api/market-platforms/`. خواندن list، detail، fields و compare برای هر کاربر JWTدار مجاز است؛ به سطح عضویت یا Trial وابسته نیست. مدیریت با همان `CONTENT_MANAGE` انجام می‌شود.
- list دارای `count/next/previous/results`، `page_size` حداکثر ۱۰۰ و ترتیب قطعی با id است. fields/ بدون pagination در `count/results` برمی‌گردد. compare فقط ۲ یا ۳ شناسهٔ فعال و هم‌نوع می‌پذیرد.
- مدل‌های Platform، FieldDefinition و PlatformChangeAudit افزوده شده‌اند. مهاجرت فقط تعریف فیلدهای پیش‌فرض را idempotent می‌سازد؛ پلتفرم/امتیاز/لینک واقعی ایجاد نمی‌کند و brokers قدیمی را تغییر نمی‌دهد.
- لوگو فقط PNG/JPEG/WebP واقعی تا ۵ MiB است. نام ذخیره‌سازی تصادفی است. حذف پلتفرم soft-delete است؛ فایل رسانه‌ای قبلی پاک نمی‌شود. `details` در PATCH به‌صورت جزئی merge می‌شود؛ پاک‌کردن یک مقدار با رشتهٔ خالی ممکن است.
- آکادمی در V2 برای دوره‌های منتشرشده و marketدار، Trial فعال یا بازار انتخاب‌شده را می‌پذیرد، حتی اگر هنوز grant مدیریتی نباشد. همهٔ دوره‌های آکادمی اکنون بدون خرید قابل مشاهده‌اند؛ دورهٔ بدون market به‌صورت حدسی باز نمی‌شود. مجوزهای VIP و سایر محتوا عوض نشده‌اند.

## انتشار بدون دست‌کاری دادهٔ واقعی

۱. `git status --short` و بکاپ قابل‌بازگشت کد/DB را بررسی کنید. فقط وقتی تغییرات روی شاخهٔ مورد انتظار و بکاپ موفق است، fetch/fast-forward کنید.
۲. `manage.py check`، `manage.py makemigrations --check --dry-run`، `manage.py migrate --plan` و سپس `manage.py migrate --noinput` را اجرا کنید. migration جدید `market_platforms.0001_initial` است. `migrate --check` را تأیید کنید.
۳. سرویس API را restart و health را بررسی کنید. health فقط سلامت سرویس است، نه اثبات CRUD.
۴. با JWT مدیر: `GET /api/market-platforms/manage/fields/?platform_type=BROKER` باید ۱۰ تعریف بدهد. یک پلتفرم واقعیِ تأییدشده را از پنل ثبت کنید؛ با JWT کاربر `GET /api/market-platforms/` و compare همان رکوردها را بررسی کنید. برای آزمایش تولید دادهٔ ساختگی نسازید.
۵. پیش از ادعای رفع کامل آکادمی، شمارش read-only دوره‌های منتشرشده را برحسب market انجام دهید:

```bash
/srv/trading-platform/venv/bin/python /srv/trading-platform/backend/manage.py shell -c "from django.db.models import Count; from apps.academy.models import Course; print(list(Course.objects.filter(status='PUBLISHED').values('market','is_free').annotate(n=Count('id')).order_by('market','is_free')))"
```

دوره‌های market خالی را مدیر باید موردبه‌مورد با market صحیح ویرایش کند. این تغییر خودکار نیست. سپس با یک کاربر دارای Trial فعال یا بازار انتخابی، list/detail/session را جداگانه تأیید کنید؛ برای دورهٔ پولی وضعیت خرید را هم بررسی کنید.

## بخش مستقل لندینگ

مشکل `https://sokanex.com/cms-api/v1/articles/` در سرور/مخزن مستقل لندینگ است و با انتشار این بک‌اند اصلاح نمی‌شود. برای آن باید کد serializer پاسخ list و detail، cache لندینگ و مسیر رسانهٔ همان پروژه در اختیار باشد؛ هیچ تغییر حدسی در API مقالات اپ اعمال نشده است.
