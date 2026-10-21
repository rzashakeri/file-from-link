"""Bilingual UI strings (en/fa). The user picks a language once via inline
glass buttons; it is stored in the DB and every bot/worker message uses it.
Add a language by copying a dict — keys must stay identical across languages."""
LANGUAGES = {"en": "🇬🇧 English", "fa": "🇮🇷 فارسی"}
DEFAULT_LANG = "en"
STRINGS = {
  "en": {
    "choose_language": "🌐 Choose your language / زبان خود را انتخاب کنید",
    "welcome": "📥 File From Link — send a link, get a file!\nSend me a video link (YouTube, Instagram, TikTok, X and 1,700+ sites), pick a quality, and the file lands right here. When it is busy, jobs wait in a fair queue.",
    "no_url": "I could not find a link in that message. Send a full URL.",
    "quality_question": "🎬 {url}\nWhich quality should I download?",
    "fmt_best": "🎬 Best quality", "fmt_720": "📺 720p", "fmt_480": "📺 480p", "fmt_audio": "🎵 Audio only (MP3)",
    "queued_adding": "⏳ Adding you to the queue…",
    "queued": "⏳ You are in the queue — position: {pos}\nJob ID: {jid}",
    "queue_full": "🚦 Your queue is full. Wait for your current jobs to finish.",
    "expired": "⏰ That request expired — send the link again.",
    "downloading": "⬇️ Downloading… {pct}%",
    "uploading": "⬆️ Sending to Telegram…",
    "done": "✅ Done: {title}",
    "failed": "❌ Download failed:\n{error}",
    "failed_generic": "❌ Something went wrong while downloading. Please try again.",
    "too_big": "📦 “{title}” is bigger than Telegram's 50MB bot limit ({mb}MB).\nDownload link (valid {hours}h):\n{url}",
    "language_set": "✅ Language set to English. Send me a link whenever you are ready!",
    "direct_link": "🔗 Direct link from the source (expires in a few hours and may not open from every network):\n{url}",
  },
  "fa": {
    "choose_language": "🌐 Choose your language / زبان خود را انتخاب کنید",
    "welcome": "📥 فایل از لینک — لینک بفرست، فایل بگیر!\nلینک ویدیو رو بفرست (یوتیوب، اینستاگرام، تیک‌تاک، X و ۱۷۰۰+ سایت)، کیفیت رو انتخاب کن و فایل رو همینجا تحویل بگیر. وقتی شلوغ باشه، کارها به نوبت توی صف می‌رن.",
    "no_url": "توی این پیام لینکی پیدا نکردم. یک URL کامل بفرست.",
    "quality_question": "🎬 {url}\nبا چه کیفیتی دانلود کنم؟",
    "fmt_best": "🎬 بهترین کیفیت", "fmt_720": "📺 720p", "fmt_480": "📺 480p", "fmt_audio": "🎵 فقط صدا (MP3)",
    "queued_adding": "⏳ در حال اضافه کردن به صف…",
    "queued": "⏳ توی صف هستی — نوبت: {pos}\nشناسه کار: {jid}",
    "queue_full": "🚦 صف تو پره. صبر کن کارهای قبلی تموم بشن.",
    "expired": "⏰ این درخواست منقضی شده — لینک رو دوباره بفرست.",
    "downloading": "⬇️ در حال دانلود… {pct}٪",
    "uploading": "⬆️ در حال ارسال به تلگرام…",
    "done": "✅ انجام شد: {title}",
    "failed": "❌ دانلود ناموفق بود:\n{error}",
    "failed_generic": "❌ خطای غیرمنتظره هنگام دانلود. دوباره تلاش کن.",
    "too_big": "📦 «{title}» بزرگ‌تر از سقف ۵۰MB تلگرام است ({mb}MB).\nلینک دانلود ({hours} ساعت معتبر):\n{url}",
    "language_set": "✅ زبان فارسی شد. هر وقت آماده‌ای لینک بفرست!",
    "direct_link": "🔗 لینک مستقیم از خود منبع (چند ساعت بیشتر معتبر نیست و ممکنه از همه شبکه‌ها باز نشه):\n{url}",
  },
}
def t(lang: str, key: str, **kw) -> str:
    s = STRINGS.get(lang, STRINGS[DEFAULT_LANG]).get(key) or STRINGS[DEFAULT_LANG][key]
    return s.format(**kw) if kw else s
def fmt_label(lang: str, choice: str) -> str:
    return t(lang, f"fmt_{choice}")
