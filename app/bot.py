"""Mode A (default): the bot runs ON EC2 via long-polling. No Serverless needed.
Language flow: a new user first picks a language with inline glass buttons
(English / فارسی); the choice is stored and EVERY message after that —
welcome, quality picker, queue position, progress, delivery — uses it.
Change it anytime with /language."""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from .config import BOT_TOKEN
from .utils import extract_urls, FORMAT_ORDER
from .queue import enqueue, QueueFull
from . import db
from .i18n import LANGUAGES, t, fmt_label
logging.basicConfig(level=logging.INFO)
PENDING: dict[int, str] = {}
def _is_youtube(url: str) -> bool:
    return "youtube.com" in url or "youtu.be" in url
async def _enqueue_direct(q, chat_id, user_id, url, lang):
    """Non-YouTube links skip the picker: straight to best-quality (HD)."""
    msg = await q.edit_message_text(t(lang, "direct_start"))
    try:
        jid, pos = enqueue(chat_id, user_id, url, "best", msg.message_id, lang)
        await q.edit_message_text(t(lang, "queued", pos=pos, jid=jid))
    except QueueFull:
        await q.edit_message_text(t(lang, "queue_full"))

def lang_markup():
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=f"lang:{code}")]
                                 for code, label in LANGUAGES.items()])
def quality_markup(lang):
    return InlineKeyboardMarkup([[InlineKeyboardButton(fmt_label(lang, k), callback_data=f"dl:{k}")]
                                 for k in FORMAT_ORDER])
def lang_of(u: Update):
    return db.get_lang(u.effective_user.id)

async def start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    lang = lang_of(u)
    if not lang:
        await u.message.reply_text(t("en", "choose_language"), reply_markup=lang_markup())
    else:
        await u.message.reply_text(t(lang, "welcome"),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🌐 Language / زبان", callback_data="langmenu")]]))
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
        await q.edit_message_text(t(lang, "quality_question", url=url), reply_markup=quality_markup(lang))
    elif url:
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
    if _is_youtube(url):
        PENDING[u.effective_chat.id] = url
        await u.message.reply_text(t(lang, "quality_question", url=url), reply_markup=quality_markup(lang))
    else:
        msg = await u.message.reply_text(t(lang, "direct_start"))
        try:
            jid, pos = enqueue(u.effective_chat.id, u.effective_user.id, url, "best", msg.message_id, lang)
            await msg.edit_text(t(lang, "queued", pos=pos, jid=jid))
        except QueueFull:
            await msg.edit_text(t(lang, "queue_full"))
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
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start)); app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("language", language_cmd))
    app.add_handler(CallbackQueryHandler(on_lang_pick, pattern=r"^lang:"))
    app.add_handler(CallbackQueryHandler(on_lang_menu, pattern=r"^langmenu$"))
    app.add_handler(CallbackQueryHandler(on_pick, pattern=r"^dl:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.run_polling(drop_pending_updates=True)
if __name__ == "__main__": main()
