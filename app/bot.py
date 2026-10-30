"""Mode A (default): the bot runs ON EC2 via long-polling. No Serverless needed.
Language flow: a new user first picks a language with inline glass buttons
(English / فارسی / Русский / العربية); the choice is stored and EVERY message
after that — welcome, quality picker, queue position, progress, delivery —
uses it. Change it anytime with /language."""
import asyncio, io, logging
import secrets
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, InputFile, InlineQueryResultsButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, InlineQueryHandler, ContextTypes, filters, TypeHandler, ApplicationHandlerStop
import json as _json
from telegram.request import HTTPXRequest
import time as _time
from .config import BOT_TOKEN, OWNER_ID, PUBLIC_DIR, BOT_API_BASE_URL
from .utils import extract_urls, FORMAT_ORDER, ig_profile_username, is_ig_story, is_spotify, is_apple_music
from .queue import enqueue, QueueFull, enqueue_broadcast
from . import db
from .i18n import LANGUAGES, t, fmt_label
from .position_updates import position_loop
from .downloader import list_qualities, list_qualities_generic
from .ig import fetch_profile_pic
logging.basicConfig(level=logging.INFO)
PENDING: dict[int, str] = {}
def _is_youtube(url: str) -> bool:
    return "youtube.com" in url or "youtu.be" in url
def _is_x(url: str) -> bool:
    return "x.com" in url or "twitter.com" in url
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
        await u.message.reply_document(document=InputFile(io.BytesIO(pic), filename=f"{username}.jpg"), caption=f"@{username}")
        await msg.delete()
    except Exception:
        await msg.edit_text(t(lang, "pic_failed"))

def lang_markup():
    items = list(LANGUAGES.items())
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(label, callback_data=f"lang:{code}") for code, label in items[i:i + 2]]
         for i in range(0, len(items), 2)])
def quality_markup(lang, show_gif=False):
    rows = [[InlineKeyboardButton(fmt_label(lang, k), callback_data=f"dl:{k}")]
            for k in FORMAT_ORDER]
    if show_gif: rows.append([InlineKeyboardButton("🎞 GIF", callback_data="dl:gif")])
    return InlineKeyboardMarkup(rows)
def dynamic_markup(lang, qualities, show_gif=False):
    rows = []
    for q in qualities[:8]:
        label = f"📹 {q['height']}p" + (f" · ~{q['mb']:.0f} MB" if q.get("mb") else "")
        rows.append([InlineKeyboardButton(label, callback_data=f"dl:h{q['height']}")])
    for a in ("audiohq", "audio", "audiolow"):
        rows.append([InlineKeyboardButton(fmt_label(lang, a), callback_data=f"dl:{a}")])
    if show_gif: rows.append([InlineKeyboardButton("🎞 GIF", callback_data="dl:gif")])
    return InlineKeyboardMarkup(rows)
async def probe_markup(lang, url):
    """Buttons from the video's REAL formats; falls back to the static list.
    YouTube gets the rich multi-client probe; every other site gets one
    quick generic probe (2026-10-22: the quality picker is back for ALL
    sites, per user requests)."""
    try:
        probe = list_qualities if _is_youtube(url) else list_qualities_generic
        qualities = await asyncio.wait_for(asyncio.to_thread(probe, url), timeout=25)
    except Exception:
        qualities = []  # timeout or probe error -> static picker, never a hang
    show_gif = _is_x(url)
    return dynamic_markup(lang, qualities, show_gif) if qualities else quality_markup(lang, show_gif)
def lang_of(u: Update):
    return db.get_lang(u.effective_user.id)

async def start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if c.args:
        url = db.take_inline_token(c.args[0])
        if url:
            await on_message(u, c, url); return
        if len(c.args[0]) == 16 and all(ch in "0123456789abcdef" for ch in c.args[0]):
            # Consumed inline token: stay silent. The button only exists in
            # the live inline results panel, so a consumed token is always
            # a second tap on the same button (or a duplicate delivery of
            # the first tap) — and the first tap already produced the
            # picker/queue flow. Any message here is pure noise, and
            # silence also keeps a repeat tap from ever duplicating a job.
            return
    lang = lang_of(u)
    if not lang:
        await u.message.reply_text(t("en", "choose_language"), reply_markup=lang_markup())
    else:
        await u.message.reply_text(t(lang, "welcome"),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "language_button"), callback_data="langmenu"),
                                                InlineKeyboardButton(t(lang, "settings_button"), callback_data="set:open")]]))
BC_STATE: dict[int, dict] = {}
def _admin_markup(lang):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "btn_stats"), callback_data="adm:stats")],
        [InlineKeyboardButton(t(lang, "btn_broadcast"), callback_data="adm:bcast")]])
def _is_owner(u: Update) -> bool:
    return bool(OWNER_ID) and u.effective_user and u.effective_user.id == OWNER_ID
async def admin_cmd(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(u): return
    lang = lang_of(u) or "fa"
    ADMIN_STATE[u.effective_chat.id] = {"stage": "menu"}
    await u.message.reply_text(t(lang, "admin_panel"), reply_markup=_admin_kb(lang))
async def on_admin(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    if not _is_owner(u): return
    lang = lang_of(u) or "fa"
    chat = u.effective_chat.id
    action = q.data.split(":", 1)[1]
    if action == "stats":
        await q.edit_message_text(await _admin_stats_text(lang), reply_markup=_admin_markup(lang))
    elif action == "menu":
        BC_STATE.pop(chat, None)
        await q.edit_message_text(t(lang, "admin_panel"), reply_markup=_admin_markup(lang))
    elif action == "bcast":
        BC_STATE[chat] = {"stage": "await_msg"}
        await q.edit_message_text(t(lang, "broadcast_prompt"),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_cancel"), callback_data="adm:cancel")]]))
    elif action == "cancel":
        BC_STATE.pop(chat, None)
        await q.edit_message_text(t(lang, "cancelled"), reply_markup=_admin_markup(lang))
    elif action == "go":
        st = BC_STATE.pop(chat, None)
        if not st or "message_id" not in st:
            await q.edit_message_text(t(lang, "expired"), reply_markup=_admin_markup(lang)); return
        n = len(db.all_user_ids())
        msg = await q.edit_message_text(t(lang, "broadcast_started", n=n))
        enqueue_broadcast(chat, st["from_chat"], st["message_id"], msg.message_id, lang)
ADMIN_STATE: dict[int, dict] = {}
def _admin_kb(lang):
    return ReplyKeyboardMarkup([
        [t(lang, "btn_stats")],
        [t(lang, "btn_broadcast")],
        [t(lang, "btn_exit_admin")]], resize_keyboard=True)
def _admin_back_kb(lang):
    return ReplyKeyboardMarkup([[t(lang, "btn_back")]], resize_keyboard=True)
def _admin_confirm_kb(lang):
    return ReplyKeyboardMarkup([[t(lang, "btn_send_all")], [t(lang, "btn_back")]], resize_keyboard=True)
async def _admin_stats_text(lang):
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
    return t(lang, "stats", storage=storage, **s)
async def _admin_keyboard(u: Update, c: ContextTypes.DEFAULT_TYPE):
    """Group -1: the ONLY group -1 handler (2026-10-27 bug: two group -1
    handlers meant the first one's filters matched every non-command
    message, so this one never ran and admin button taps fell through
    to on_message's no_url reply). It serves both admin flows:
    (a) the legacy inline broadcast capture (BC_STATE), and
    (b) the reply-keyboard admin panel (ADMIN_STATE).
    Only active while the owner is inside an admin flow; any other
    message falls through to the normal handlers, so the owner can
    still use the bot while the keyboard is up. Back buttons abandon
    the current step and return to the admin menu; Exit removes the
    keyboard entirely. The old inline admin callbacks above keep
    working for messages sent before this change."""
    if not _is_owner(u) or not u.effective_message: return
    chat = u.effective_chat.id
    lang = lang_of(u) or "fa"
    text = u.effective_message.text or ""
    # (a) Legacy inline broadcast capture.
    bcs = BC_STATE.get(chat)
    if bcs and bcs.get("stage") == "await_msg":
        BC_STATE[chat] = {"stage": "await_confirm", "from_chat": chat, "message_id": u.effective_message.message_id}
        n = len(db.all_user_ids())
        markup = InlineKeyboardMarkup([[
            InlineKeyboardButton(t(lang, "btn_send_all"), callback_data="adm:go"),
            InlineKeyboardButton(t(lang, "btn_cancel"), callback_data="adm:cancel")]])
        await u.effective_message.reply_text(t(lang, "broadcast_confirm", n=n), reply_markup=markup)
        raise ApplicationHandlerStop
    # (b) Reply-keyboard panel. If the keyboard outlived a bot restart
    # (keyboards persist client-side, ADMIN_STATE does not), an admin
    # button tap re-enters the menu instead of falling through.
    st = ADMIN_STATE.get(chat)
    if not st:
        if text in (t(lang, "btn_stats"), t(lang, "btn_broadcast"), t(lang, "btn_exit_admin")):
            ADMIN_STATE[chat] = {"stage": "menu"}
            st = ADMIN_STATE[chat]
        else:
            return
    stage = st.get("stage")
    if stage == "menu":
        if text == t(lang, "btn_stats"):
            await u.effective_message.reply_text(await _admin_stats_text(lang), reply_markup=_admin_kb(lang))
            raise ApplicationHandlerStop
        if text == t(lang, "btn_broadcast"):
            ADMIN_STATE[chat] = {"stage": "await_msg"}
            await u.effective_message.reply_text(t(lang, "broadcast_prompt"), reply_markup=_admin_back_kb(lang))
            raise ApplicationHandlerStop
        if text == t(lang, "btn_exit_admin"):
            ADMIN_STATE.pop(chat, None)
            await u.effective_message.reply_text(t(lang, "admin_exited"), reply_markup=ReplyKeyboardRemove())
            raise ApplicationHandlerStop
        return
    if stage == "await_msg":
        if text == t(lang, "btn_back"):
            ADMIN_STATE[chat] = {"stage": "menu"}
            await u.effective_message.reply_text(t(lang, "admin_panel"), reply_markup=_admin_kb(lang))
            raise ApplicationHandlerStop
        ADMIN_STATE[chat] = {"stage": "await_confirm", "from_chat": chat, "message_id": u.effective_message.message_id}
        n = len(db.all_user_ids())
        await u.effective_message.reply_text(t(lang, "broadcast_confirm", n=n), reply_markup=_admin_confirm_kb(lang))
        raise ApplicationHandlerStop
    if stage == "await_confirm":
        if text == t(lang, "btn_send_all"):
            st = ADMIN_STATE.pop(chat, None)
            if not st or "message_id" not in st:
                ADMIN_STATE[chat] = {"stage": "menu"}
                await u.effective_message.reply_text(t(lang, "expired"), reply_markup=_admin_kb(lang))
                raise ApplicationHandlerStop
            n = len(db.all_user_ids())
            msg = await u.effective_message.reply_text(t(lang, "broadcast_started", n=n), reply_markup=_admin_kb(lang))
            ADMIN_STATE[chat] = {"stage": "menu"}
            enqueue_broadcast(chat, st["from_chat"], st["message_id"], msg.message_id, lang)
            raise ApplicationHandlerStop
        if text == t(lang, "btn_back"):
            ADMIN_STATE[chat] = {"stage": "menu"}
            await u.effective_message.reply_text(t(lang, "admin_panel"), reply_markup=_admin_kb(lang))
            raise ApplicationHandlerStop
        await u.effective_message.reply_text(t(lang, "broadcast_confirm", n=len(db.all_user_ids())), reply_markup=_admin_confirm_kb(lang))
        raise ApplicationHandlerStop
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
    lang = lang_of(u) or "en"
    await u.message.reply_text(t(lang, "choose_language"), reply_markup=lang_markup())
SETTINGS_CHOICES = ("best", "720", "480", "audio")
def _settings_markup(lang):
    rows = [[InlineKeyboardButton(fmt_label(lang, k), callback_data=f"set:{k}") for k in ("best", "720")],
            [InlineKeyboardButton(fmt_label(lang, k), callback_data=f"set:{k}") for k in ("480", "audio")],
            [InlineKeyboardButton(t(lang, "settings_clear"), callback_data="set:clear")]]
    return InlineKeyboardMarkup(rows)
def _settings_text(lang, current):
    if current:
        return t(lang, "settings_title") + "\n" + t(lang, "settings_current", fmt=fmt_label(lang, current))
    return t(lang, "settings_title") + "\n" + t(lang, "settings_none")
async def settings_cmd(u: Update, c: ContextTypes.DEFAULT_TYPE):
    lang = lang_of(u) or "en"
    await u.message.reply_text(_settings_text(lang, db.get_default_fmt(u.effective_user.id)), reply_markup=_settings_markup(lang))
async def on_settings(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    lang = lang_of(u) or "en"
    action = q.data.split(":", 1)[1]
    if action == "open":
        await q.edit_message_text(_settings_text(lang, db.get_default_fmt(u.effective_user.id)), reply_markup=_settings_markup(lang))
    elif action == "clear":
        db.set_default_fmt(u.effective_user.id, None)
        await q.edit_message_text(t(lang, "settings_cleared"))
    else:
        if action not in SETTINGS_CHOICES: action = "best"
        db.set_default_fmt(u.effective_user.id, action)
        await q.edit_message_text(t(lang, "settings_saved", fmt=fmt_label(lang, action)))
async def on_lang_menu(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    lang = lang_of(u) or "en"
    await q.edit_message_text(t(lang, "choose_language"), reply_markup=lang_markup())
async def on_lang_pick(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    lang = q.data.split(":", 1)[1]
    if lang not in LANGUAGES: lang = "en"
    db.set_lang(u.effective_user.id, lang)
    url = PENDING.pop(u.effective_chat.id, None)
    if url and not is_spotify(url) and not is_apple_music(url) and not ig_profile_username(url) and not is_ig_story(url):
        default_fmt = db.get_default_fmt(u.effective_user.id)
        if default_fmt:
            msg = await q.edit_message_text(t(lang, "queued_adding"))
            try:
                jid, pos = enqueue(u.effective_chat.id, u.effective_user.id, url, default_fmt, msg.message_id, lang)
                await q.edit_message_text(t(lang, "queued", pos=pos, jid=jid))
            except QueueFull:
                await q.edit_message_text(t(lang, "queue_full"))
        else:
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
                await c.bot.send_document(u.effective_chat.id, document=InputFile(io.BytesIO(pic), filename=f"{username}.jpg"), caption=f"@{username}")
                await q.edit_message_text(t(lang, "language_set"))
            except Exception:
                await q.edit_message_text(t(lang, "pic_failed"))
        elif is_spotify(url) or is_apple_music(url):
            await _enqueue_direct(q, u.effective_chat.id, u.effective_user.id, url, lang, "audio")
        else:
            await _enqueue_direct(q, u.effective_chat.id, u.effective_user.id, url, lang)
    else:
        await q.edit_message_text(t(lang, "language_set") + "\n\n" + t(lang, "welcome"))
async def on_message(u: Update, c: ContextTypes.DEFAULT_TYPE, _url=None):
    urls = [_url] if _url else extract_urls(u.message.text or "")
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
    if is_spotify(url) or is_apple_music(url):
        await _direct_message(u, url, lang, "audio"); return
    if is_ig_story(url):
        await _direct_message(u, url, lang); return
    default_fmt = db.get_default_fmt(u.effective_user.id)
    if default_fmt:
        msg = await u.message.reply_text(t(lang, "queued_adding"))
        try:
            jid, pos = enqueue(u.effective_chat.id, u.effective_user.id, url, default_fmt, msg.message_id, lang)
            await msg.edit_text(t(lang, "queued", pos=pos, jid=jid))
        except QueueFull:
            await msg.edit_text(t(lang, "queue_full"))
        return
    PENDING[u.effective_chat.id] = url
    msg = await u.message.reply_text(t(lang, "probing"))
    markup = await probe_markup(lang, url)
    await msg.edit_text(t(lang, "quality_question", url=url), reply_markup=markup)
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
async def on_inline_query(u: Update, c: ContextTypes.DEFAULT_TYPE):
    """Inline funnel: answer fast with a button that opens the bot, never a
    download. Telegram only waits seconds for an inline answer and a
    download takes minutes (longer with a queue), so the button carries
    a one-hour token for the link; /start redeems it into the normal
    flow. Empty results + button = nothing junk posted in the
    chat the query came from. Language: the user's stored language, else
    their Telegram language code, else English. PTB 22 replaced the old
    switch_pm_text/switch_pm_parameter with InlineQueryResultsButton."""
    q = u.inline_query
    lang = db.get_lang(q.from_user.id)
    if not lang:
        code = (q.from_user.language_code or "en")[:2]
        lang = code if code in LANGUAGES else "en"
    urls = extract_urls(q.query or "")
    if urls:
        token = secrets.token_hex(8)
        db.save_inline_token(token, urls[0])
        await q.answer([], button=InlineQueryResultsButton(text=t(lang, "inline_download"), start_parameter=token), cache_time=0)
    else:
        await q.answer([], button=InlineQueryResultsButton(text=t(lang, "inline_open"), start_parameter="inline"), cache_time=0)
async def on_togif(u: Update, c: ContextTypes.DEFAULT_TYPE):
    """Done-message 'Convert to GIF': re-queue the same URL as a real-.gif
    job. The done message keeps its settings/language buttons; only the
    convert button is removed so a double-tap cannot double-queue."""
    q = u.callback_query
    lang = lang_of(u) or "en"
    job_id = q.data.split(":", 1)[1]
    job = db.get_job(job_id)
    if not job or job.get("user_id") != u.effective_user.id:
        await q.answer(t(lang, "failed_generic")); return
    await q.answer()
    try:
        await q.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "settings_button"), callback_data="set:open"), InlineKeyboardButton(t(lang, "language_button"), callback_data="langmenu")]]))
    except Exception:
        pass
    msg = await q.message.reply_text(t(lang, "queued_adding"))
    try:
        jid, pos = enqueue(u.effective_chat.id, u.effective_user.id, job["url"], "togif", msg.message_id, lang)
        await msg.edit_text(t(lang, "queued", pos=pos, jid=jid))
    except QueueFull:
        await msg.edit_text(t(lang, "queue_full"))
DEBUG_LOG = "/data/updates.log"
def _dbg(rec):
    try:
        with open(DEBUG_LOG, "a") as f: f.write(_json.dumps(rec) + "\n")
    except Exception:
        pass
async def _error_handler(u, c):
    _dbg({"kind": "error", "err": str(c.error)[:300]})
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
    asyncio.create_task(position_loop(app.bot))
def main():
    # Hardened polling: the 2026-10-22 stall was a silently hung long-poll
    # (container Up, zero errors, no updates for 40+ min). Explicit HTTP
    # timeouts make a half-open connection RAISE instead of hanging, and
    # bootstrap_retries=-1 makes the updater retry forever on its own.
    # Local Bot API server: route PTB through it too (polling + messages)
    # and give writes room for large sends; unset = cloud defaults.
    write_timeout = 1800 if BOT_API_BASE_URL else 30
    req = HTTPXRequest(connect_timeout=10, read_timeout=30, write_timeout=write_timeout, pool_timeout=10)
    gu_req = HTTPXRequest(connect_timeout=10, read_timeout=45, write_timeout=30, pool_timeout=10)
    # concurrent_updates is THE fix for the promo-day freezes: PTB processes
    # updates SEQUENTIALLY by default, so one user's 30-90s quality probe
    # queued every other user's reply behind it (~1 min freeze, then a burst).
    # With concurrency on, each update runs in its own task and the ack goes
    # out immediately; heavy work stays in the workers regardless.
    builder = Application.builder().token(BOT_TOKEN).concurrent_updates(True).request(req)
    if BOT_API_BASE_URL:
        base_file = (BOT_API_BASE_URL[:-len("/bot")] + "/file/bot" if BOT_API_BASE_URL.endswith("/bot")
                     else BOT_API_BASE_URL + "/file/bot")
        builder = builder.base_url(BOT_API_BASE_URL).base_file_url(base_file)
    app = builder.get_updates_request(gu_req).post_init(_post_init).build()
    app.add_error_handler(_error_handler)
    app.add_handler(CommandHandler("start", start)); app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("language", language_cmd))
    app.add_handler(CommandHandler("settings", settings_cmd))
    app.add_handler(CallbackQueryHandler(on_settings, pattern=r"^set:"))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CallbackQueryHandler(on_admin, pattern=r"^adm:"))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, _admin_keyboard), group=-1)
    app.add_handler(CallbackQueryHandler(on_lang_pick, pattern=r"^lang:"))
    app.add_handler(CallbackQueryHandler(on_lang_menu, pattern=r"^langmenu$"))
    app.add_handler(CallbackQueryHandler(on_pick, pattern=r"^dl:"))
    app.add_handler(CallbackQueryHandler(on_togif, pattern=r"^togif:"))
    app.add_handler(InlineQueryHandler(on_inline_query))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.run_polling(drop_pending_updates=False, timeout=30, bootstrap_retries=-1)  # False: never eat user messages across a restart (2026-10-22: the owner's /stats sent during a stall were silently discarded by True)
if __name__ == "__main__": main()
