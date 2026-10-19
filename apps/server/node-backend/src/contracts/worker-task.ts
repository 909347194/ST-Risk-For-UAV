// A2A Contract — WorkerTask（单源设计：zod schema 为真相源，TS 类型由 schema 推导）
// 设计定稿中的统一任务对象。Planner 通过工具把模型参数包成 WorkerTask，经 Router 分发给 Worker。
// 运行期校验用 parseWorkerTask（见 contracts/runtime-schema.ts）；每个领域的强类型 input/output 在各自 Worker 模块内定义。

import { z } from 'zod';

/** Worker 执行状态：成功 / 部分成功 / 失败 / 需人工补充信息。 */
export const workerStatusSchema = z.enum(['success', 'partial', 'failed', 'need_input']);
export type WorkerStatus = z.infer<typeof workerStatusSchema>;

/** 反馈类型：失败/冲突/建议 → 由 Feedback Handler 转成 dispatch_events。 */
export const feedbackTypeSchema = z.enum([
  'replan',
  'reallocate',
  'reroute',
  'reassess_risk',
  'need_information',
  'none',
]);
export type FeedbackType = z.infer<typeof feedbackTypeSchema>;

/** WorkerTask 边界 schema（分发前由 parseWorkerTask 校验）。 */
export const workerTaskSchema = z.object({
  /** 本次工具调用的唯一 ID（由 Planner/Orchestrator 生成，推荐 pi 导出的 uuidv7）。 */
  taskId: z.string(),
  /** pi 的 toolCallId：把「工具调用 ↔ WorkerTask ↔ worker_executions 落库记录」三方可关联。 */
  correlationId: z.string(),
  /** 所属调度计划 ID。 */
  planId: z.string(),
  /** 本次执行 Run ID。 */
  runId: z.string(),
  /** 执行者类型，如 allocation-worker / risk-worker。 */
  workerType: z.string(),
  /** 能力标识，如 allocation.assign（Planner 优先按能力请求）。 */
  capability: z.string(),
  /** 任务目标描述，供 Worker 理解意图。 */
  objective: z.string(),
  /** 领域输入（由模型/Orchestrator 提供，运行期需用 zod 校验）。 */
  input: z.unknown(),
  /** 第几次尝试（用于重试与反馈闭环）。 */
  attempt: z.number(),
  /** Contract 版本，随 schema 演进递增。 */
  schemaVersion: z.string(),
});

type WorkerTaskBase = z.infer<typeof workerTaskSchema>;

/** 统一任务对象；`input` 可携带领域强类型参数。 */
export type WorkerTask<TInput = unknown> = Omit<WorkerTaskBase, 'input'> & {
  /** 领域输入（运行期需用 zod 校验）。 */
  input: TInput;
};
