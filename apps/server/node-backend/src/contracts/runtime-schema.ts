// Contract 边界运行时校验（zod）— 见 docs/architecture/agent-architecture-node-landing.md §6.2
//
// 分工：TypeBox 管工具参数（pi 运行时自动校验）；zod 只在 pi 之外的边界兜底：
//   ① WorkerRuntime 返回的 WorkerResult（Router 回收时校验）
//   ② Python 服务响应（AlgorithmClient 回收时校验）
//   ③ 模型/Orchestrator 构造 WorkerTask 时的领域 input 兜底
// TS 接口本身不能验证运行期数据，这一层必须有。

import { z } from 'zod';

import type { WorkerTask } from '@/contracts/worker-task';
import type { WorkerResult } from '@/contracts/worker-result';

export const workerStatusSchema = z.enum(['success', 'partial', 'failed', 'need_input']);
export const feedbackTypeSchema = z.enum([
  'replan',
  'reallocate',
  'reroute',
  'reassess_risk',
  'need_information',
  'none',
]);

export const workerFeedbackSchema = z.object({
  type: feedbackTypeSchema,
  reason: z.string(),
  affectedTaskIds: z.array(z.string()).optional(),
});

export const workerErrorSchema = z.object({
  code: z.string(),
  message: z.string(),
  retryable: z.boolean(),
});

/** WorkerResult 边界 schema（与 contracts/worker-result.ts 的 interface 同步演进）。 */
export const workerResultSchema = z.object({
  taskId: z.string(),
  correlationId: z.string().optional(),
  planId: z.string(),
  runId: z.string(),
  workerType: z.string(),
  capability: z.string().optional(),
  attempt: z.number().optional(),
  durationMs: z.number().optional(),
  status: workerStatusSchema,
  result: z.unknown().optional(),
  feedback: workerFeedbackSchema.optional(),
  error: workerErrorSchema.optional(),
});

/** WorkerTask 边界 schema（模型参数包成任务后、分发前校验）。 */
export const workerTaskSchema = z.object({
  taskId: z.string(),
  correlationId: z.string(),
  planId: z.string(),
  runId: z.string(),
  workerType: z.string(),
  capability: z.string(),
  objective: z.string(),
  input: z.unknown(),
  attempt: z.number(),
  schemaVersion: z.string(),
});

/** 校验并归一 WorkerResult；失败抛 zod 错误（在 Router/Orchestrator 边界炸掉，别把脏数据传给 Planner）。 */
export function parseWorkerResult(value: unknown): WorkerResult {
  return workerResultSchema.parse(value) as WorkerResult;
}

/** 校验 WorkerTask；在 dispatch 分发前调用。 */
export function parseWorkerTask(value: unknown): WorkerTask {
  return workerTaskSchema.parse(value) as WorkerTask;
}
