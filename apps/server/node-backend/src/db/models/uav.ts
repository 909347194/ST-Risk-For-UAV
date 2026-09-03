// ORM 模型 — UAV 表（PostGIS 几何列）

import { pgTable, text, real, geometry } from 'drizzle-orm/pg-core';

export const uavs = pgTable('uavs', {
  id: text('id').primaryKey(),
  position: geometry('position', { type: 'point', srid: 4326 }).notNull(),
  speed: real('speed').notNull(),
  maxPayload: real('max_payload').notNull(),
  battery: real('battery').notNull(),
  status: text('status').notNull().default('idle'),
});
