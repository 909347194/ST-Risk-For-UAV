// ORM 模型 — Task 表

import { sqliteTable, text, real } from 'drizzle-orm/sqlite-core';

export const tasks = sqliteTable('tasks', {
  id: text('id').primaryKey(),
  x: real('x').notNull(),
  y: real('y').notNull(),
  z: real('z').notNull().default(0),
  priority: text('priority').notNull().default('medium'),
  payloadWeight: real('payload_weight').notNull(),
  timeLimit: real('time_limit'),
});
