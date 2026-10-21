import { table, integer, text } from 'sdk/db';
export const pending = table('pending', {
  chatId: integer('chat_id').primaryKey(),
  url: text('url').notNull(),
  created: integer('created_at').notNull().default(0),
});
