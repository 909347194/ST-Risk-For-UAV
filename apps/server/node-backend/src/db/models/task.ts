// ORM 模型 — 任务表（PostGIS 几何列）

import { pgTable, text, real, integer, geometry } from 'drizzle-orm/pg-core';

export const tasks = pgTable('tasks', {
  id: text('id').primaryKey(),
  position: geometry('position', { type: 'point', srid: 4326 }).notNull(),
  priority: text('priority').notNull().default('medium'),
  payloadWeight: real('payload_weight').notNull(),
  timeLimit: integer('time_limit'),  // 秒，可选
  status: text('status').notNull().default('pending'),
});
