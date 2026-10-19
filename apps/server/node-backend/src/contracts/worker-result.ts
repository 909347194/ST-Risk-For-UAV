// A2A Contract — WorkerResult（单源设计：zod schema 为真相源，TS 类型由 schema 推导）
// Worker 通过统一 Contract 返回结果/反馈。Planner 根据 feedback 决定全局下一步（继续/重规划/结束）。

import { z } from 'zod';

import { feedbackTypeSchema, workerStatusSchema } from './worker-task';

/** WorkerResult 边界 schema（Router/网关回收处由 parseWorkerResult 校验）。 */
export const workerResultSchema = z.object({
  /** 与请求对应的任务 ID。 */
  taskId: z.string(),
  /** pi toolCallId 对齐的关联 ID（通常由调用方回填，见 workerResultToToolResult）。 */
  correlationId: z.string().optional(),
  planId: z.string(),
  runId: z.string(),
  /** 执行者类型。 */
  workerType: z.string(),
  /** 能力标识（从 WorkerTask 回传，便于落库/追溯）。 */
  capability: z.string().optional(),
  /** 第几次尝试（从 WorkerTask 回传）。 */
  attempt: z.number().optional(),
  /** 执行耗时（毫秒，运行指标）。 */
  durationMs: z.number().optional(),
  /** 执行状态。 */
  status: workerStatusSchema,
  /** 结构化结果（成功/部分成功时存在）。 */
  result: z.unknown().optional(),
  /** 反馈：失败/冲突/建议，由 Feedback Handler 转成事件。 */
  feedback: z
    .object({
      type: feedbackTypeSchema,
      reason: z.string(),
      /** 受影响的关联任务 ID。 */
      affectedTaskIds: z.array(z.string()).optional(),
    })
    .optional(),
  /** 错误信息（status 为 failed 时）。 */
  error: z
    .object({
      code: z.string(),
      message: z.string(),
      /** 是否可重试。 */
      retryable: z.boolean(),
    })
    .optional(),
});

type WorkerResultBase = z.infer<typeof workerResultSchema>;

/** 统一结果对象；`result` 可携带领域强类型输出。 */
export type WorkerResult<TOutput = unknown> = Omit<WorkerResultBase, 'result'> & {
  /** 结构化结果（成功/部分成功时存在）。 */
  result?: TOutput;
};
