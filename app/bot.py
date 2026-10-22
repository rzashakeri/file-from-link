"""Mode A (default): the bot runs ON EC2 via long-polling. No Serverless needed.
Language flow: a new user first picks a language with inline glass buttons
(English / فارسی); the choice is stored and EVERY message after that —
welcome, quality picker, queue position, progress, delivery — uses it.
Change it anytime with /language."""
import asyncio, io, logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.request import HTTPXRequest
import time as _time
from .config import BOT_TOKEN, OWNER_ID, PUBLIC_DIR
from .utils import extract_urls, FORMAT_ORDER, ig_profile_username, is_ig_story, is_spotify, is_apple_music
from .queue import enqueue, QueueFull
from . import db
from .i18n import LANGUAGES, t, fmt_label
from .downloader import list_qualities
from .ig import fetch_profile_pic
logging.basicConfig(level=logging.INFO)
PENDING: dict[int, str] = {}
def _is_youtube(url: str) -> bool:
    return "youtube.com" in url or "youtu.be" in url
async def _enqueue_direct(q, chat_id, user_id, url, lang, fmt="best"):
    """Non-YouTube links skip the picker: straight to the download."""
    msg = await q.edit_message_text(t(lang, "direct_start"))
    try:
        jid, pos = enqueue(chat_id, user_id, url, fmt, msg.message_id, lang)
        await q.edit_message_text(t(lang, "queued", pos=pos, jid=jid))
    except QueueFull:
        await q.edit_message_text(t(lang, "queue_full"))
async def _direct_message(u, url, lang, fmt="best"):
    msg = await u.message.reply_text(t(lang, "direct_start"))
    try:
        jid, pos = enqueue(u.effective_chat.id, u.effective_user.id, url, fmt, msg.message_id, lang)
        await msg.edit_text(t(lang, "queued", pos=pos, jid=jid))
    except QueueFull:
        await msg.edit_text(t(lang, "queue_full"))
async def _send_profile_pic(u, username, lang):
    msg = await u.message.reply_text(t(lang, "fetching_pic"))
    try:
        pic = await asyncio.to_thread(fetch_profile_pic, username)
        await u.message.reply_photo(photo=io.BytesIO(pic), caption=f"@{username}")
        await msg.delete()
    except Exception:
        await msg.edit_text(t(lang, "pic_failed"))

def lang_markup():
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=f"lang:{code}")]
                                 for code, label in LANGUAGES.items()])
def quality_markup(lang):
    return InlineKeyboardMarkup([[InlineKeyboardButton(fmt_label(lang, k), callback_data=f"dl:{k}")]
                                 for k in FORMAT_ORDER])
def dynamic_markup(lang, qualities):
    rows = []
    for q in qualities[:8]:
        label = f"📹 {q['height']}p" + (f" · ~{q['mb']:.0f} MB" if q.get("mb") else "")
        rows.append([InlineKeyboardButton(label, callback_data=f"dl:h{q['height']}")])
    rows.append([InlineKeyboardButton(fmt_label(lang, "audio"), callback_data="dl:audio")])
    rows.append([InlineKeyboardButton(fmt_label(lang, "audiolow"), callback_data="dl:audiolow")])
    return InlineKeyboardMarkup(rows)
async def probe_markup(lang, url):
    """Buttons from the video's REAL formats; falls back to the static list."""
    try:
        qualities = await asyncio.to_thread(list_qualities, url)
    except Exception:
        qualities = []
    return dynamic_markup(lang, qualities) if qualities else quality_markup(lang)
def lang_of(u: Update):
    return db.get_lang(u.effective_user.id)

async def start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    lang = lang_of(u)
    if not lang:
        await u.message.reply_text(t("en", "choose_language"), reply_markup=lang_markup())
    else:
        await u.message.reply_text(t(lang, "welcome"),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🌐 Language / زبان", callback_data="langmenu")]]))
async def stats_cmd(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if not OWNER_ID or u.effective_user.id != OWNER_ID:
        return  # owner-only: silent for everyone else
    s = db.stats()
    total = 0
    try:
        for r, _dirs, files in __import__("os").walk(PUBLIC_DIR):
            for f in files:
                try: total += __import__("os").path.getsize(__import__("os").path.join(r, f))
                except OSError: pass
    except Exception:
        pass
    storage = f"{total/1073741824:.1f} GB" if total >= 1073741824 else f"{total//1048576} MB"
    await u.message.reply_text(t(lang_of(u) or "fa", "stats", storage=storage, **s))
async def language_cmd(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.message.reply_text(t("en", "choose_language"), reply_markup=lang_markup())
async def on_lang_menu(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    await q.edit_message_text(t("en", "choose_language"), reply_markup=lang_markup())
async def on_lang_pick(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    lang = q.data.split(":", 1)[1]
    if lang not in LANGUAGES: lang = "en"
    db.set_lang(u.effective_user.id, lang)
    url = PENDING.pop(u.effective_chat.id, None)
    if url and _is_youtube(url):
        PENDING[u.effective_chat.id] = url
        await q.edit_message_text(t(lang, "probing"))
        markup = await probe_markup(lang, url)
        await q.edit_message_text(t(lang, "quality_question", url=url), reply_markup=markup)
    elif url:
        username = ig_profile_username(url)
        if username:
            await q.edit_message_text(t(lang, "fetching_pic"))
            try:
                pic = await asyncio.to_thread(fetch_profile_pic, username)
                await c.bot.send_photo(u.effective_chat.id, photo=io.BytesIO(pic), caption=f"@{username}")
                await q.edit_message_text(t(lang, "language_set"))
            except Exception:
                await q.edit_message_text(t(lang, "pic_failed"))
        elif is_spotify(url) or is_apple_music(url):
            await _enqueue_direct(q, u.effective_chat.id, u.effective_user.id, url, lang, "audio")
        else:
            await _enqueue_direct(q, u.effective_chat.id, u.effective_user.id, url, lang)
    else:
        await q.edit_message_text(t(lang, "language_set") + "\n\n" + t(lang, "welcome"))
async def on_message(u: Update, c: ContextTypes.DEFAULT_TYPE):
    urls = extract_urls(u.message.text or "")
    lang = lang_of(u)
    if not urls:
        await u.message.reply_text(t(lang or "en", "no_url")); return
    url = urls[0]
    if not lang:
        PENDING[u.effective_chat.id] = url
        await u.message.reply_text(t("en", "choose_language"), reply_markup=lang_markup()); return
    username = ig_profile_username(url)
    if username:
        await _send_profile_pic(u, username, lang); return
    if _is_youtube(url):
        PENDING[u.effective_chat.id] = url
        msg = await u.message.reply_text(t(lang, "probing"))
        markup = await probe_markup(lang, url)
        await msg.edit_text(t(lang, "quality_question", url=url), reply_markup=markup)
    elif is_spotify(url) or is_apple_music(url):
        await _direct_message(u, url, lang, "audio")
    else:
        await _direct_message(u, url, lang)
async def on_pick(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    lang = lang_of(u) or "en"
    url = PENDING.pop(u.effective_chat.id, None)
    if not url: await q.edit_message_text(t(lang, "expired")); return
    fmt = q.data.split(":", 1)[1]
    msg = await q.edit_message_text(t(lang, "queued_adding"))
    try:
        jid, pos = enqueue(u.effective_chat.id, u.effective_user.id, url, fmt, msg.message_id, lang)
        await q.edit_message_text(t(lang, "queued", pos=pos, jid=jid))
    except QueueFull:
        await q.edit_message_text(t(lang, "queue_full"))
HEARTBEAT_PATH = "/data/bot_heartbeat"
async def _heartbeat_loop():
    """Touch a heartbeat file every 60s so the host watchdog can tell a
    live event loop from a dead one."""
    while True:
        try:
            with open(HEARTBEAT_PATH, "w") as f: f.write(str(int(_time.time())))
        except Exception:
            pass
        await asyncio.sleep(60)
async def _post_init(app):
    asyncio.create_task(_heartbeat_loop())
def main():
    # Hardened polling: the 2026-10-22 stall was a silently hung long-poll
    # (container Up, zero errors, no updates for 40+ min). Explicit HTTP
    # timeouts make a half-open connection RAISE instead of hanging, and
    # bootstrap_retries=-1 makes the updater retry forever on its own.
    req = HTTPXRequest(connect_timeout=10, read_timeout=30, write_timeout=30, pool_timeout=10)
    gu_req = HTTPXRequest(connect_timeout=10, read_timeout=45, write_timeout=30, pool_timeout=10)
    app = (Application.builder().token(BOT_TOKEN)
           .request(req).get_updates_request(gu_req).post_init(_post_init).build())
    app.add_handler(CommandHandler("start", start)); app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("language", language_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CallbackQueryHandler(on_lang_pick, pattern=r"^lang:"))
    app.add_handler(CallbackQueryHandler(on_lang_menu, pattern=r"^langmenu$"))
    app.add_handler(CallbackQueryHandler(on_pick, pattern=r"^dl:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.run_polling(drop_pending_updates=True, timeout=30, bootstrap_retries=-1)
if __name__ == "__main__": main()
