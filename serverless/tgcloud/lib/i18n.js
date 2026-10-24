// Front-end strings (en/fa/ru/ar). The Telegram client language picks one;
// delivery/worker messages use the same lang, sent with the job to EC2.
const STRINGS = {
  en: {
    welcome: "📥 File From Link — send a link, get a file!\nSend me a video link (YouTube, Instagram, TikTok, X and 1,700+ sites), pick a quality, and the file lands right here. When it is busy, jobs wait in a fair queue.",
    no_url: "I could not find a link in that message. Send a full URL.",
    quality_question: "🎬 {url}\nWhich quality should I download?",
    fmt_best: "🎬 Best quality",
    fmt_720: "📺 720p",
    fmt_480: "📺 480p",
    fmt_audio: "🎵 Audio only (MP3)",
    expired: "⏰ That request expired — send the link again.",
    queued_adding: "⏳ Adding you to the queue…",
    queued: "⏳ You are in the queue — position: {pos}\nJob ID: {jid}",
    queue_error: "❌ The EC2 queue did not respond: {error}",
  },
  fa: {
    welcome: "📥 فایل از لینک — لینک بفرست، فایل بگیر!\nلینک ویدیو رو بفرست (یوتیوب، اینستاگرام، تیک‌تاک، X و ۱۷۰۰+ سایت)، کیفیت رو انتخاب کن و فایل رو همینجا تحویل بگیر. وقتی شلوغ باشه، کارها به نوبت توی صف می‌رن.",
    no_url: "توی این پیام لینکی پیدا نکردم. یک URL کامل بفرست.",
    quality_question: "🎬 {url}\nبا چه کیفیتی دانلود کنم؟",
    fmt_best: "🎬 بهترین کیفیت",
    fmt_720: "📺 720p",
    fmt_480: "📺 480p",
    fmt_audio: "🎵 فقط صدا (MP3)",
    expired: "⏰ این درخواست منقضی شده — لینک رو دوباره بفرست.",
    queued_adding: "⏳ در حال اضافه کردن به صف…",
    queued: "⏳ توی صف هستی — نوبت: {pos}\nشناسه کار: {jid}",
    queue_error: "❌ صف EC2 جواب نداد: {error}",
  },
  ru: {
    welcome: "📥 File From Link — отправьте ссылку, получите файл!\nПришлите ссылку на видео (YouTube, Instagram, TikTok, X и более 1700 сайтов), выберите качество — и файл придёт сюда. Если сервер занят, задачи ждут в очереди.",
    no_url: "В этом сообщении нет ссылки. Отправьте полный URL.",
    quality_question: "🎬 {url}\nВ каком качестве скачать?",
    fmt_best: "🎬 Лучшее качество",
    fmt_720: "📺 720p",
    fmt_480: "📺 480p",
    fmt_audio: "🎵 Только звук (MP3)",
    expired: "⏰ Запрос устарел — отправьте ссылку ещё раз.",
    queued_adding: "⏳ Добавляю вас в очередь…",
    queued: "⏳ Вы в очереди — позиция: {pos}\nID задачи: {jid}",
    queue_error: "❌ Очередь EC2 не отвечает: {error}",
  },
  ar: {
    welcome: "📥 File From Link — أرسل رابطًا واحصل على ملف!\nأرسل رابط فيديو (YouTube وInstagram وTikTok وX وأكثر من 1700 موقع)، واختر الجودة، وسيصل الملف إلى هنا. وعند الازدحام تنتظر المهام في قائمة عادلة.",
    no_url: "لم أجد رابطًا في هذه الرسالة. أرسل عنوان URL كاملًا.",
    quality_question: "🎬 {url}\nبأي جودة أحمّل؟",
    fmt_best: "🎬 أفضل جودة",
    fmt_720: "📺 720p",
    fmt_480: "📺 480p",
    fmt_audio: "🎵 صوت فقط (MP3)",
    expired: "⏰ انتهت صلاحية هذا الطلب — أرسل الرابط مرة أخرى.",
    queued_adding: "⏳ جارٍ إضافتك إلى قائمة الانتظار…",
    queued: "⏳ أنت في قائمة الانتظار — الترتيب: {pos}\nمعرّف المهمة: {jid}",
    queue_error: "❌ قائمة انتظار EC2 لم تستجب: {error}",
  },
};
const DEFAULT_LANG = 'en';
export const FORMATS = ['best', '720', '480', 'audio'];
export function langOf(user) {
  const code = ((user && user.language_code) || '').split('-')[0].toLowerCase();
  return STRINGS[code] ? code : DEFAULT_LANG;
}
export function t(lang, key, vars = {}) {
  const s = (STRINGS[lang] || STRINGS[DEFAULT_LANG])[key] ?? STRINGS[DEFAULT_LANG][key];
  return s.replace(/\{(\w+)\}/g, (_, name) => (vars[name] ?? `{${name}}`));
}
export function fmtLabel(lang, choice) {
  return t(lang, `fmt_${choice}`);
}
