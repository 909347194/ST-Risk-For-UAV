// ORM 模型 — 飞行轨迹表（PostGIS 线几何 + pgvector）

import { pgTable, text, real, timestamp, geometry } from 'drizzle-orm/pg-core';

export const flightLogs = pgTable('flight_logs', {
  id: text('id').primaryKey(),
  uavId: text('uav_id').notNull(),
  track: geometry('track', { type: 'line', srid: 4326 }),  // PostGIS 轨迹线
  startTime: timestamp('start_time'),
  endTime: timestamp('end_time'),
  totalDistance: real('total_distance'),
  // pgvector 列需通过 raw SQL 添加（Drizzle ORM 尚不原生支持 vector 类型）
  // embedding vector(128)
});
