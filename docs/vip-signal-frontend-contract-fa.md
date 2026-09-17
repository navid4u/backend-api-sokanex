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
- تب پیش‌فرض `crypto` و تب دوم `forex` باقی بماند.
- pagination استاندارد `count/next/previous/results` حفظ شود.

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
