// ORM 模型 — Worker 执行记录表
// 每一次 Worker 调用（成功/失败/反馈）都落库，保证执行流程可追溯。替代原内存 Map。

import { integer, jsonb, pgTable, text, timestamp } from 'drizzle-orm/pg-core';

export const workerExecutions = pgTable('worker_executions', {
  id: text('id').primaryKey(),
  runId: text('run_id').notNull(),
  taskId: text('task_id').notNull(),
  /** 能力标识，如 allocation.assign。 */
  capability: text('capability').notNull(),
  /** 执行者类型，如 allocation-worker。 */
  workerType: text('worker_type').notNull(),
  attempt: integer('attempt').notNull().default(0),
  /** success / partial / failed / need_input */
  status: text('status').notNull(),
  durationMs: integer('duration_ms'),
  /** feedback.type：replan / reallocate / reroute / reassess_risk / need_information / none */
  feedbackType: text('feedback_type'),
  errorCode: text('error_code'),
  /** 结构化返回值/错误信息。 */
  details: jsonb('details'),
  createdAt: timestamp('created_at').notNull().defaultNow(),
});

export type WorkerExecutionRow = typeof workerExecutions.$inferSelect;
export type NewWorkerExecution = typeof workerExecutions.$inferInsert;
