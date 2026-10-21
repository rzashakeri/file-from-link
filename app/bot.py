"""Mode A (default): the bot runs ON EC2 via long-polling. No Serverless needed.
Mode B: enable Serverless instead and STOP this service (a bot token can only
have one update consumer pattern at a time in practice) - see DEPLOY.fa.md."""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from .config import BOT_TOKEN
from .utils import extract_urls, FORMATS
from .queue import enqueue, QueueFull
logging.basicConfig(level=logging.INFO)
PENDING: dict[int, str] = {}
async def start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.message.reply_text("📥 File From Link — send a link, get a file!\nSend me a video link (YouTube, Instagram, TikTok, X and 1,700+ sites via yt-dlp), pick a quality, and the file lands right here. Jobs are queued fairly when it gets busy.\n\nلینک ویدیو رو بفرست، کیفیت رو انتخاب کن، فایل رو همینجا تحویل بگیر 👇")
async def on_message(u: Update, c: ContextTypes.DEFAULT_TYPE):
    urls = extract_urls(u.message.text or "")
    if not urls: await u.message.reply_text("لینکی پیدا نکردم. یک URL کامل بفرست."); return
    PENDING[u.effective_chat.id] = urls[0]
    kb = [[InlineKeyboardButton(label, callback_data=f"dl:{k}")] for k,(label,_) in FORMATS.items()]
    await u.message.reply_text(f"🎬 {urls[0]}\nچه کیفیتی دانلود کنم؟", reply_markup=InlineKeyboardMarkup(kb))
async def on_pick(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    url = PENDING.pop(u.effective_chat.id, None)
    if not url: await q.edit_message_text("⏰ این درخواست منقضی شده، لینک رو دوباره بفرست."); return
    fmt = q.data.split(":",1)[1]
    msg = await q.edit_message_text("⏳ در صف قرار گرفت…")
    try:
        jid, pos = enqueue(u.effective_chat.id, u.effective_user.id, url, fmt, msg.message_id)
        await q.edit_message_text(f"⏳ توی صف هستی — نوبت: {pos}\nشناسه کار: {jid}")
    except QueueFull:
        await q.edit_message_text("🚦 صف تو پره. صبر کن کارهای قبلی تموم بشن.")
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start)); app.add_handler(CommandHandler("help", start))
    app.add_handler(CallbackQueryHandler(on_pick, pattern=r"^dl:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.run_polling(drop_pending_updates=True)
if __name__ == "__main__": main()
