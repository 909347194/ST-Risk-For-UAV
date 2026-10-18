// ORM 模型 — 调度计划表（Plan）
// 一次调度意图（火灾侦察等）对应一个 Plan；其下可有多次执行 Run。

import { jsonb, pgTable, text, timestamp } from 'drizzle-orm/pg-core';

export const plans = pgTable('plans', {
  id: text('id').primaryKey(),
  objective: text('objective').notNull(),
  /** 约束（JSON）：时间窗、区域、资源限制等。 */
  constraints: jsonb('constraints'),
  /** created / planning / executing / validating / completed / failed / cancelled */
  status: text('status').notNull().default('created'),
  createdAt: timestamp('created_at').notNull().defaultNow(),
  updatedAt: timestamp('updated_at').notNull().defaultNow(),
});

export type PlanRow = typeof plans.$inferSelect;
export type NewPlan = typeof plans.$inferInsert;
