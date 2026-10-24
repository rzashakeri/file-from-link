// Serverless front: it CANNOT run yt-dlp (V8 isolate, no Python/ffmpeg,
// fetch responses capped at 30MB). It only takes the link, shows the
// quality picker, and hands the job to the EC2 engine via /jobs.
import { api, db } from 'sdk';
import { pending } from '../schema.js';
import { langOf, t, fmtLabel, FORMATS } from '../lib/i18n.js';
const URL_RE = /https?:\/\/[^\s<>()[\]{}]+/;
export default async function (message) {
  const chatId = message.chat.id;
  const lang = langOf(message.from);
  const text = message.text || '';
  if (text.startsWith('/start') || text.startsWith('/help')) {
    await api.sendMessage({ chat_id: chatId, text: t(lang, 'welcome') });
    return;
  }
  const m = text.match(URL_RE);
  if (!m) { await api.sendMessage({ chat_id: chatId, text: t(lang, 'no_url') }); return; }
  const url = m[0].replace(/[.,;:!?]+$/, '');
  await db.insert(pending).values({ chatId, url, created: Date.now() })
    .onConflictDoUpdate({ target: pending.chatId, set: { url, created: Date.now() } }).run();
  await api.sendMessage({ chat_id: chatId, text: t(lang, 'quality_question', { url }),
    reply_markup: { inline_keyboard: FORMATS.map((k) => [{ text: fmtLabel(lang, k), callback_data: `dl:${k}` }]) } });
}
