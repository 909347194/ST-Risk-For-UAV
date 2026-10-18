// A2A Contract — WorkerResult
// Worker 通过统一 Contract 返回结果/反馈。Planner 根据 feedback 决定全局下一步（继续/重规划/结束）。

import type { FeedbackType, WorkerStatus } from './worker-task';

export interface WorkerResult<TOutput = unknown> {
  /** 与请求对应的任务 ID。 */
  taskId: string;
  planId: string;
  runId: string;
  /** 执行者类型。 */
  workerType: string;
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
