// ORM 模型 — 执行 Run 表
// 每个 Plan 的一次完整执行（含重规划）对应一个 Run。状态机：
// CREATED → PLANNING → EXECUTING → VALIDATING → COMPLETED
//                                      ↘ FAILED / CANCELLED
// 重规划 / 等待补充信息等情况通过 dispatch_events 记录，不新增状态值。

import { integer, jsonb, pgTable, text, timestamp } from 'drizzle-orm/pg-core';

export const runs = pgTable('runs', {
  id: text('id').primaryKey(),
  planId: text('plan_id').notNull().default(''),
  /** Run 状态机取值（见上）。 */
  status: text('status').notNull().default('created'),
  /** 第几次尝试（重规划/重试递增）。 */
  attempt: integer('attempt').notNull().default(0),
  /** 任意结构化结果/响应载荷（如旧的 AgentTaskResponse）。 */
  payload: jsonb('payload'),
  createdAt: timestamp('created_at').notNull().defaultNow(),
  updatedAt: timestamp('updated_at').notNull().defaultNow(),
  finishedAt: timestamp('finished_at'),
});

export type RunRow = typeof runs.$inferSelect;
export type NewRun = typeof runs.$inferInsert;
