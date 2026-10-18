// ORM 模型 — 调度事件表
// 重规划、重新分配、重试、取消、等待补充信息等全局事件流，供可追溯与复盘。

import { jsonb, pgTable, text, timestamp } from 'drizzle-orm/pg-core';

export const dispatchEvents = pgTable('dispatch_events', {
  id: text('id').primaryKey(),
  runId: text('run_id').notNull(),
  /** replan / reallocate / reroute / reassess_risk / retry / cancel / wait_info */
  type: text('type').notNull(),
  reason: text('reason'),
  payload: jsonb('payload'),
  createdAt: timestamp('created_at').notNull().defaultNow(),
});

export type DispatchEventRow = typeof dispatchEvents.$inferSelect;
export type NewDispatchEvent = typeof dispatchEvents.$inferInsert;
