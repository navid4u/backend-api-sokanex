# Sokanex VIP Signal Channel API

Production API base URL: `https://api.sokanex.com`

Authentication is server-to-server. Send the shared key in this header on every request:

```http
X-Sokanex-Signal-Key: YOUR_PRIVATE_KEY
```

Never place this key in Telegram messages, browser JavaScript, public repositories, or logs.

## Crypto channel

`POST https://api.sokanex.com/api/signals/channels/crypto/ingest/`

## Forex channel

`POST https://api.sokanex.com/api/signals/channels/forex/ingest/`

Both endpoints accept the same fields:

- `text` — required, UTF-8 text, maximum 20,000 characters.
- `image` — optional image file, maximum 8 MB.
- `external_id` — optional but strongly recommended. Use a stable value such as `channel_id:message_id`; retries with the same value do not create duplicates.
- `published_at` — optional ISO-8601 timestamp. If omitted, the server receive time is used.

Use `multipart/form-data` when sending an image. JSON is supported for text-only posts.

### cURL with image

```bash
curl -X POST "https://api.sokanex.com/api/signals/channels/crypto/ingest/" \
  -H "X-Sokanex-Signal-Key: YOUR_PRIVATE_KEY" \
  -F "external_id=-1001234567890:846" \
  -F "text=متن کامل پست تلگرام" \
  -F "published_at=2026-09-17T12:30:00+03:30" \
  -F "image=@/absolute/path/post.jpg"
```

For Forex, only change `crypto` to `forex` in the URL.

### cURL text only

```bash
curl -X POST "https://api.sokanex.com/api/signals/channels/forex/ingest/" \
  -H "X-Sokanex-Signal-Key: YOUR_PRIVATE_KEY" \
  -H "Content-Type: application/json" \
  --data '{"external_id":"-1009876543210:125","text":"متن کامل پست فارکس"}'
```

### Python example

```python
import requests

url = "https://api.sokanex.com/api/signals/channels/crypto/ingest/"
headers = {"X-Sokanex-Signal-Key": "YOUR_PRIVATE_KEY"}
data = {
    "external_id": f"{telegram_channel_id}:{telegram_message_id}",
    "text": telegram_post_text,
}

if image_path:
    with open(image_path, "rb") as image_file:
        response = requests.post(
            url,
            headers=headers,
            data=data,
            files={"image": ("telegram.jpg", image_file, "image/jpeg")},
            timeout=30,
        )
else:
    response = requests.post(url, headers=headers, json=data, timeout=30)

response.raise_for_status()
result = response.json()
```

### Response and retries

- `201 Created`: a new post was created.
- `200 OK`: the same `external_id` was already received; the existing post is returned.
- `400 Bad Request`: missing/invalid text, image, or timestamp.
- `401 Unauthorized`: missing or incorrect API key.
- `413 Request Entity Too Large`: proxy/server upload limit is smaller than the file.
- `429 Too Many Requests`: sending rate exceeded; retry with exponential backoff.
- `503 Service Unavailable`: server ingestion is not configured.

Successful response:

```json
{
  "id": 42,
  "kind": "VIP_CHANNEL_POST",
  "channel": "CRYPTO",
  "channel_label": "کانال وی آی پی سوکانکس (کریپتو)",
  "text": "متن کامل پست تلگرام",
  "excerpt": "۳۰ کلمه اول متن…",
  "image": "https://api.sokanex.com/media/signals/vip/crypto/example.jpg",
  "source": "TELEGRAM_API",
  "published_at": "2026-09-17T12:30:00+03:30",
  "created_at": "2026-09-17T12:30:03+03:30"
}
```

The robot must retry only connection failures, `429`, and `5xx`. Reuse the same `external_id` on every retry. Do not retry validation `400` or authentication `401` until the request/key is corrected.

