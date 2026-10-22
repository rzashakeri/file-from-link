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
    "fmt_best": "🎬 Best quality", "fmt_720": "📺 720p", "fmt_480": "📺 480p", "fmt_audiohq": "🎵 MP3 · 320kbps (best audio)", "fmt_audio": "🎵 MP3 · 192kbps", "fmt_audiolow": "🗜️ MP3 · 48kbps (tiny, low bandwidth)",
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
    "probing": "🔍 Checking the qualities this video actually has…",
    "matching": "🔍 Finding this track on YouTube…",
    "fetching_pic": "🖼️ Fetching the profile picture…",
    "pic_failed": "❌ Could not fetch that profile picture (private account or Instagram blocked the request).",
    "stats": "📊 Bot statistics\n👥 Total users: {users}\n⬇️ Total downloads: {jobs} (today: {today})\n✅ Done: {done} · ❌ Failed: {failed}\n💾 Public files on disk: {storage}",
    "direct_start": "⬇️ Got it! Downloading the best quality (HD) — no need to pick anything.",
    "direct_link": "🔗 Direct link from the source (expires in a few hours and may not open from every network):\n{url}",
    "footer": "📥 Downloaded via @FileFromLinkBot",
    "description": "📝 Description",
  },
  "fa": {
    "choose_language": "🌐 Choose your language / زبان خود را انتخاب کنید",
    "welcome": "📥 فایل از لینک — لینک بفرست، فایل بگیر!\nلینک ویدیو رو بفرست (یوتیوب، اینستاگرام، تیک‌تاک، X و ۱۷۰۰+ سایت)، کیفیت رو انتخاب کن و فایل رو همینجا تحویل بگیر. وقتی شلوغ باشه، کارها به نوبت توی صف می‌رن.",
    "no_url": "توی این پیام لینکی پیدا نکردم. یک URL کامل بفرست.",
    "quality_question": "🎬 {url}\nبا چه کیفیتی دانلود کنم؟",
    "fmt_best": "🎬 بهترین کیفیت", "fmt_720": "📺 720p", "fmt_480": "📺 480p", "fmt_audiohq": "🎵 MP3 · کیفیت ۳۲۰ (بهترین صدا)", "fmt_audio": "🎵 MP3 · کیفیت ۱۹۲", "fmt_audiolow": "🗜️ MP3 · کیفیت ۴۸ (کم‌حجم، برای اینترنت ضعیف)",
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
    "probing": "🔍 دارم کیفیت‌هایی که این ویدیو واقعاً داره رو بررسی می‌کنم…",
    "matching": "🔍 دارم این آهنگ رو توی یوتیوب پیدا می‌کنم…",
    "fetching_pic": "🖼️ دارم عکس پروفایل رو می‌گیرم…",
    "pic_failed": "❌ نشد عکس پروفایل رو بگیرم (پیج پرایوته یا اینستاگرام درخواست رو بلاک کرد).",
    "stats": "📊 آمار بات\n👥 کل کاربرها: {users}\n⬇️ کل دانلودها: {jobs} (امروز: {today})\n✅ موفق: {done} · ❌ ناموفق: {failed}\n💾 فایل‌های عمومی روی دیسک: {storage}",
    "direct_start": "⬇️ گرفتم! دارم با بهترین کیفیت (HD) دانلود می‌کنم — نیازی به انتخاب نیست.",
    "direct_link": "🔗 لینک مستقیم از خود منبع (چند ساعت بیشتر معتبر نیست و ممکنه از همه شبکه‌ها باز نشه):\n{url}",
    "footer": "📥 دریافت شده از @FileFromLinkBot",
    "description": "📝 توضیحات",
  },
}
def t(lang: str, key: str, **kw) -> str:
    s = STRINGS.get(lang, STRINGS[DEFAULT_LANG]).get(key) or STRINGS[DEFAULT_LANG][key]
    return s.format(**kw) if kw else s
def fmt_label(lang: str, choice: str) -> str:
    return t(lang, f"fmt_{choice}")
