# ارسال یک‌بارهٔ متن اصلاح‌شدهٔ روز اول کمپین Trial

این عملیات فقط برای کمپین ثابت `all_normal_users_2026_10_29` است. تاریخ شروع/پایان Trial و روزهای ۲ تا ۷ عوض نمی‌شوند. مطابق تأیید مالک، کسانی که پیام روز اول قبلی را گرفته‌اند **پیام دوم** دریافت می‌کنند. ارسال‌های قبلی و شناسه‌های پیامیتو دست‌نخورده می‌مانند. ردیف‌های قدیمیِ `PENDING` به `SKIPPED` با علت `DAY1_REISSUED_WITH_NEW_TEXT` تبدیل می‌شوند و متن تازه در ردیف‌های جدید و با event key ثابت، یک‌بار صف می‌شود. حساب غیرفعال، شمارهٔ نامعتبر/ناموجود و Trial دیگر نامعتبر پیامک نمی‌گیرند و با علت مشخص ثبت می‌شوند.

## قبل از اجرا

۱. تایمر و سرویس SMS Automation باید خاموش باشند و تا پایان تأیید متن روشن نشوند. OTP جداست و با این توقف قطع نمی‌شود.

```bash
systemctl is-enabled sokanex-sms-automation.timer
systemctl is-active sokanex-sms-automation.timer sokanex-sms-automation.service
```

خروجی باید `disabled` و دو بار `inactive` باشد. فرمان apply روی لینوکس این وضعیت را خودش نیز بررسی می‌کند.

۲. متن روز ۱ را در پنل «مسیر هفت‌روزه» ویرایش و ذخیره کنید. ویرایش سناریوی عمومی `WELCOME` متن Journey را تغییر نمی‌دهد.

۳. از دیتابیس بکاپ بگیرید و کد جدید را با `git merge --ff-only` استقرار دهید. هیچ migration جدیدی برای این تغییر نیست. قبل از apply، `manage.py check` و `migrate --check` را اجرا کنید. چون تایمر خاموش است، استقرار کد به‌تنهایی پیامکی نمی‌فرستد.

## پیش‌نمایش بدون ارسال

```bash
cd /srv/trading-platform/backend
MARKET_ACCESS_V2_ENABLED=True /srv/trading-platform/venv/bin/python manage.py reissue_trial_day_one_sms_20261029 --actor superadmin
```

خروجی، `day_one_text` و زمان ویرایش، شمارش گیرندگان، تعداد کسانی که پیام دوم می‌گیرند، وضعیت قدیمی‌ها، تعداد `other_pending_messages_outside_this_campaign` و دو digest مبهم را نشان می‌دهد. متن را **بصری تأیید** کنید. اگر `already_applied=true` یا `original_status_counts.SENDING>0` است، عملیات را ادامه ندهید. اگر `other_pending_messages_outside_this_campaign>0` است، آن صف جداگانه را پیش از روشن‌کردن کارگر بررسی کنید؛ این فرمان فقط پیام‌های روز اول کمپین ثابت را جایگزین می‌کند.

## اعمال با اعداد واقعی پیش‌نمایش

فقط بعد از تأیید متن، شمارش و هزینهٔ پیام دوم، با اعداد واقعی پیش‌نمایش اجرا کنید. `N`، `AUDIENCE_SHA` و `TEXT_SHA` نمونه نیستند و باید با خروجی خود سرور جایگزین شوند:

```bash
MARKET_ACCESS_V2_ENABLED=True /srv/trading-platform/venv/bin/python manage.py reissue_trial_day_one_sms_20261029 --actor superadmin --apply --confirm-resend-to-previous-recipients --confirm-worker-stopped --expected-old-pending N --expected-candidate-digest AUDIENCE_SHA --expected-template-digest TEXT_SHA
```

این عملیات اتمیک است؛ اگر متن، مخاطبان، تعداد پیام‌های قدیمیِ در صف یا وضعیت کارگر تغییر کرده باشد، بدون نوشتن داده متوقف می‌شود. اجرای دوبارهٔ همان عملیات، ردیف جدید یا پیام دومِ دوم نمی‌سازد.

## بعد از اعمال، هنوز بدون ارسال

```bash
/srv/trading-platform/venv/bin/python manage.py shell -c "from django.db.models import Count; from apps.notifications.models import SMSAutomationDelivery as D; from apps.accounts.models import TrialCampaign; c=TrialCampaign.objects.get(operation_key='all_normal_users_2026_10_29'); q=D.objects.filter(event='JOURNEY_REISSUE',event_key__startswith='JOURNEY_REISSUE:%s:1:'%c.pk); print('new_reissue=',list(q.values('status','failure_code').annotate(n=Count('id')).order_by('status','failure_code'))); print('old_pending_for_campaign=',D.objects.filter(event='JOURNEY',status='PENDING',event_key__in=['JOURNEY:%s:1:SMS'%i for i in c.grants.values_list('pk',flat=True)]).count())"
```

قبل از روشن‌کردن تایمر، باید `old_pending_for_campaign=0` باشد. در صورت خطا یا اختلاف شمارش، **کارگر را روشن نکنید** و خروجی را بررسی کنید. بعد از تأیید نهایی مالک، تایمر را فعال کنید؛ `send_pending` حداکثر ۱۰۰ مورد در هر نوبت پنج‌دقیقه‌ای می‌فرستد. `SENT` به‌معنی پذیرش پیامیتو است، نه تأیید تحویل به گوشی. وضعیت `SENDING` بعد از قطع غیرمنتظره باید دستی بررسی شود و نباید کورکورانه retry شود.

## اگر تایمر `active (elapsed)` و `Trigger: n/a` دارد

نسخهٔ قدیمی تایمر با `OnBootSec` و `OnUnitActiveSec` پس از توقف و فعال‌سازی دوباره ممکن است نوبت بعدی نداشته باشد. فایل `deployment/systemd/sokanex-sms-automation.timer` اصلاح شده است: نخستین نوبت دو دقیقه بعد از فعال‌شدن تایمر و نوبت‌های بعدی پنج دقیقه بعد از پایان هر اجرای سرویس تعیین می‌شوند. این تغییر فقط زمان‌بندی را اصلاح می‌کند؛ ردیف‌های SMS و تاریخ Trial را دست‌کاری نمی‌کند.

```bash
cd /srv/trading-platform/backend
git fetch origin backend-with-frontedits
git merge --ff-only origin/backend-with-frontedits
install -m 0644 deployment/systemd/sokanex-sms-automation.timer /etc/systemd/system/sokanex-sms-automation.timer
systemctl daemon-reload
systemctl restart sokanex-sms-automation.timer
systemctl list-timers --all --no-pager | grep -F sokanex-sms-automation
```

ستون `NEXT` باید زمان واقعی داشته باشد، نه `n/a`. پس از نوبت بعد، `systemctl show sokanex-sms-automation.service -p Result -p ExecMainStatus --no-pager` و `journalctl -u sokanex-sms-automation.service --since "10 minutes ago" -n 20 --no-pager` را بررسی کنید. `Result=success` قدیمی، اجرای نوبت جدید را ثابت نمی‌کند.
