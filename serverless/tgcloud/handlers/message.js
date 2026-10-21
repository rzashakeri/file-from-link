// Serverless front: it CANNOT run yt-dlp (V8 isolate, no Python/ffmpeg,
// fetch responses capped at 30MB). It only takes the link, shows the
// quality picker, and hands the job to the EC2 engine via /jobs.
import { api, db } from 'sdk';
import { pending } from '../schema.js';
const URL_RE = /https?:\/\/[^\s<>()[\]{}]+/;
const FORMATS = [
  ['best', '🎬 بهترین کیفیت'], ['720', '📺 720p'],
  ['480', '📺 480p'], ['audio', '🎵 فقط صدا (MP3)'],
];
export default async function (message) {
  const chatId = message.chat.id;
  const text = message.text || '';
  if (text.startsWith('/start') || text.startsWith('/help')) {
    await api.sendMessage({ chat_id: chatId,
      text: '📥 File From Link — send a link, get a file! Send a video link (YouTube, Instagram, TikTok, X, 1,700+ sites), pick a quality — your file lands right here. لینک بفرست، فایل بگیر 👇' });
    return;
  }
  const m = text.match(URL_RE);
  if (!m) { await api.sendMessage({ chat_id: chatId, text: 'لینکی پیدا نکردم. یک URL کامل بفرست.' }); return; }
  const url = m[0].replace(/[.,;:!?]+$/, '');
  await db.insert(pending).values({ chatId, url, created: Date.now() })
    .onConflictDoUpdate({ target: pending.chatId, set: { url, created: Date.now() } }).run();
  await api.sendMessage({ chat_id: chatId, text: `🎬 ${url}\nچه کیفیتی دانلود کنم؟`,
    reply_markup: { inline_keyboard: FORMATS.map(([k, label]) => [{ text: label, callback_data: `dl:${k}` }]) } });
}
