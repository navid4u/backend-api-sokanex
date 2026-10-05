# قرارداد فرانت رسانه‌های کانال سیگنال VIP

endpointهای فعلی بدون تغییر باقی می‌مانند:

```text
GET /api/signals/?channel=crypto
GET /api/signals/?channel=forex
GET /api/signals/{id}/
```

درخواست‌ها با JWT فعلی کاربر ارسال شوند. فرانت هرگز نباید کلید
`X-Sokanex-Signal-Key` را دریافت یا ارسال کند.

هر آیتم علاوه بر فیلدهای قبلی دارای رسانه‌های nullable زیر است:

```json
{
  "image": "https://api.sokanex.com/media/...webp",
  "video": "https://api.sokanex.com/media/...mp4",
  "audio": "https://api.sokanex.com/media/...oga"
}
```

- `null` یعنی رسانه وجود ندارد؛ placeholder شکسته نمایش داده نشود.
- URLها absolute هستند؛ آن‌ها را concat یا بازسازی نکنید.
- ویدئو با `controls`, `playsInline`, `preload="metadata"` و بدون autoplay نمایش داده شود.
- صدا با `controls`, `preload="metadata"` و بدون autoplay نمایش داده شود.
- failure یک رسانه نباید کارت یا صفحه را crash کند؛ فقط همان media block مدیریت شود.
- متن و excerpt مانند قبل نمایش داده شوند و HTML آن‌ها اجرا نشود.
- پست رسانه‌ای می‌تواند `text: ""` و `excerpt: ""` داشته باشد؛ کارت را به‌خاطر متن خالی حذف نکنید و رسانه/نقل‌قول را همچنان نمایش دهید.
- پس از دریافت پروفایل، اگر `user.market_type === "forex"` بود تب اولیه `forex` باشد؛ در بقیه حالت‌ها `crypto`. هر بار `channel` را صریح در query بفرستید و انتخاب دستی کاربر را با refresh خودکار پروفایل عوض نکنید.
- اگر `channel` ارسال نشود، بک‌اند نیز بر اساس `request.user.market_type` فارکس یا کریپتو را پیش‌فرض می‌کند؛ این fallback جای انتخاب و نمایش درست تب در فرانت را نمی‌گیرد.
- pagination استاندارد `count/next/previous/results` حفظ شود.
- `reply_to_external_id` شناسه پایدار Telegram است و URL پست داخل اپ نیست.
- `reply_preview` اگر null باشد، پست Reply نیست. اگر `available=true` و `id` عددی باشد، نقل‌قول به `/signals/{id}` لینک شود. در `available=false` فقط نقل‌قول ذخیره‌شده یا «پیام مرجع در دسترس نیست» نمایش داده شود؛ لینک نسازید.
- متن `reply_preview.text` را فقط به‌صورت متن ساده render کنید. فایل/رسانه داخل نقل‌قول از `media_type` فقط با نشانگر نوع رسانه نمایش داده شود.
- Reply هم در همان لیست بازار خودش می‌آید؛ هیچ درخواست جداگانه‌ای برای ساخت Reply از مرورگر نزنید.

TypeScript:

```ts
export interface VipSignalPost {
  id: number;
  kind: "VIP_CHANNEL_POST";
  channel: "CRYPTO" | "FOREX";
  channel_label: string;
  text: string;
  excerpt: string;
  image: string | null;
  video: string | null;
  audio: string | null;
  source: "TELEGRAM_API";
  reply_to_external_id: string | null;
  reply_preview: null | {
    id: number | null;
    text: string | null;
    media_type: "image" | "video" | "audio" | null;
    available: boolean;
  };
  published_at: string;
  created_at: string;
}
```

React:

```tsx
{post.image && <img src={post.image} alt="" loading="lazy" />}
{post.video && (
  <video controls playsInline preload="metadata">
    <source src={post.video} />
  </video>
)}
{post.audio && (
  <audio controls preload="metadata">
    <source src={post.audio} />
  </audio>
)}
```

endpoint جداگانه‌ای برای دریافت صدا یا ویدئو لازم نیست؛ URL رسانه همراه همان نتیجه می‌آید.
