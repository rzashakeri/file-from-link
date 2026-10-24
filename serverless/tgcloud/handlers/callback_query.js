import { api, db } from 'sdk';
import { eq } from 'sdk/db';
import { pending } from '../schema.js';
import { enqueueOnEc2 } from '../lib/ec2.js';
import { langOf, t } from '../lib/i18n.js';
export default async function (query) {
  const chatId = query.message.chat.id;
  await api.answerCallbackQuery({ callback_query_id: query.id });
  const lang = langOf(query.from);
  const fmt = (query.data || '').split(':')[1] || 'best';
  const rows = await db.select().from(pending).where(eq(pending.chatId, chatId)).run();
  if (!rows.length) {
    await api.editMessageText({ chat_id: chatId, message_id: query.message.message_id, text: t(lang, 'expired') });
    return;
  }
  const msg = await api.editMessageText({ chat_id: chatId, message_id: query.message.message_id, text: t(lang, 'queued_adding') });
  try {
    const job = await enqueueOnEc2({ chat_id: chatId, user_id: query.from.id, url: rows[0].url, fmt, lang,
                                     status_message_id: query.message.message_id });
    await api.editMessageText({ chat_id: chatId, message_id: query.message.message_id,
      text: t(lang, 'queued', { pos: job.position, jid: job.job_id }) });
  } catch (e) {
    await api.editMessageText({ chat_id: chatId, message_id: query.message.message_id,
      text: t(lang, 'queue_error', { error: e.message }) });
  }
}
