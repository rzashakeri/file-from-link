import { api, db } from 'sdk';
import { eq } from 'sdk/db';
import { pending } from '../schema.js';
import { enqueueOnEc2 } from '../lib/ec2.js';
export default async function (query) {
  const chatId = query.message.chat.id;
  await api.answerCallbackQuery({ callback_query_id: query.id });
  const fmt = (query.data || '').split(':')[1] || 'best';
  const rows = await db.select().from(pending).where(eq(pending.chatId, chatId)).run();
  if (!rows.length) {
    await api.editMessageText({ chat_id: chatId, message_id: query.message.message_id, text: '⏰ این درخواست منقضی شده، لینک رو دوباره بفرست.' });
    return;
  }
  const msg = await api.editMessageText({ chat_id: chatId, message_id: query.message.message_id, text: '⏳ در صف قرار گرفت…' });
  try {
    const job = await enqueueOnEc2({ chat_id: chatId, user_id: query.from.id, url: rows[0].url, fmt,
                                     status_message_id: query.message.message_id });
    await api.editMessageText({ chat_id: chatId, message_id: query.message.message_id,
      text: `⏳ توی صف هستی — نوبت: ${job.position}\nشناسه کار: ${job.job_id}` });
  } catch (e) {
    await api.editMessageText({ chat_id: chatId, message_id: query.message.message_id,
      text: `❌ صف EC2 جواب نداد: ${e.message}` });
  }
}
