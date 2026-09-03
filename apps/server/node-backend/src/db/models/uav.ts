// ORM 模型 — UAV 表

import { sqliteTable, text, real } from 'drizzle-orm/sqlite-core';

export const uavs = sqliteTable('uavs', {
  id: text('id').primaryKey(),
  x: real('x').notNull(),
  y: real('y').notNull(),
  z: real('z').notNull().default(0),
  speed: real('speed').notNull(),
  maxPayload: real('max_payload').notNull(),
  battery: real('battery').notNull(),
  status: text('status').notNull().default('idle'),
});
