// A2A Contract — WorkerResult
// Worker 通过统一 Contract 返回结果/反馈。Planner 根据 feedback 决定全局下一步（继续/重规划/结束）。

import type { FeedbackType, WorkerStatus } from './worker-task';

export interface WorkerResult<TOutput = unknown> {
  /** 与请求对应的任务 ID。 */
  taskId: string;
  /** pi toolCallId 对齐的关联 ID（通常由调用方回填，见 workerResultToToolResult）。 */
  correlationId?: string;
  planId: string;
  runId: string;
  /** 执行者类型。 */
  workerType: string;
  /** 能力标识（从 WorkerTask 回传，便于落库/追溯）。 */
  capability?: string;
  /** 第几次尝试（从 WorkerTask 回传）。 */
  attempt?: number;
  /** 执行耗时（毫秒，运行指标）。 */
  durationMs?: number;
  /** 执行状态。 */
  status: WorkerStatus;
  /** 结构化结果（成功/部分成功时存在）。 */
  result?: TOutput;
  /** 反馈：失败/冲突/建议，由 Feedback Handler 转成事件。 */
  feedback?: {
    type: FeedbackType;
    reason: string;
    /** 受影响的关联任务 ID。 */
    affectedTaskIds?: string[];
  };
  /** 错误信息（status 为 failed 时）。 */
  error?: {
    code: string;
    message: string;
    /** 是否可重试。 */
    retryable: boolean;
  };
}
