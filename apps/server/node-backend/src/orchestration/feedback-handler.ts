// Feedback Handler = pi 的 `afterToolCall` 钩子（见 docs/architecture/agent-architecture-node-landing.md 第 7.2 节）。
//
// 遵循 pi：工具结果的后处理/落库就是 afterToolCall 的职责——每次工具执行完（无论成败）
// 把结果落到 worker_executions，把 WorkerResult.feedback 转成 dispatch_events，形成可追溯执行流。
// 不自研"事件总线/回调注册中心"；模型侧的反馈感知由工具结果（isError/terminate）与转录天然承载。
//
// 端口用结构化窄接口（DispatchRepository 天然满足）；本文件只 `import type`，无运行时 ESM 依赖。

import type { AfterToolCallContext, AfterToolCallResult } from '@earendil-works/pi-agent-core';
import type { NewDispatchEvent, NewWorkerExecution } from '@/db/models';
import type { WorkerResult } from '@/contracts/worker-result';

/** 落库端口（由 services/db/dispatch.repo.ts 的 DispatchRepository 注入满足）。 */
export interface DispatchRecordSink {
  recordWorkerExecution(input: NewWorkerExecution): Promise<unknown>;
  appendEvent(input: NewDispatchEvent): Promise<unknown>;
}

/** 工具执行计时登记：start 于 beforeToolCall 放行时，take 于 afterToolCall 落库时。 */
export class ToolExecutionTracker {
  private readonly startedAt = new Map<string, number>();

  start(toolCallId: string): void {
    this.startedAt.set(toolCallId, Date.now());
  }

  /** 取出并清除某次工具调用的耗时（毫秒）；无记录返回 undefined。 */
  takeDurationMs(toolCallId: string): number | undefined {
    const started = this.startedAt.get(toolCallId);
    if (started === undefined) return undefined;
    this.startedAt.delete(toolCallId);
    return Date.now() - started;
  }
}

export interface FeedbackHandlerOptions {
  /** 当前 Run ID（结果里缺失 runId 时兜底）。 */
  runId: string;
  /** 落库端口。 */
  sink: DispatchRecordSink;
  /** 主键生成器（建议注入 pi 的 uuidv7；默认 randomUUID 兜底）。 */
  genId?: () => string;
  /** 计时登记（与 createBeforeToolCallHook 的 tracker 共用同一实例）。 */
  tracker?: ToolExecutionTracker;
  /** 落库失败不应打断 Agent 运行；错误走此回调（默认 console.error）。 */
  onError?: (error: unknown) => void;
}

function defaultGenId(): string {
  // 运行期兜底；正常装配时应注入 pi 的 uuidv7（时间有序）。
  return globalThis.crypto?.randomUUID?.() ?? `id-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

/**
 * 构造 pi `afterToolCall` 钩子（执行追溯 + 反馈事件）。
 * 总是返回 undefined（不改写工具结果）；落库失败只上报 onError，不影响 Agent 运行。
 */
export function createAfterToolCallHook(
  options: FeedbackHandlerOptions,
): (
  context: AfterToolCallContext,
  signal?: AbortSignal,
) => Promise<AfterToolCallResult | undefined> {
  const genId = options.genId ?? defaultGenId;
  const handleError = options.onError ?? ((error: unknown) => console.error('[feedback-handler]', error));

  return async ({ toolCall, result, isError }: AfterToolCallContext) => {
    try {
      const details = result.details as WorkerResult | undefined;
      const runId = details?.runId || options.runId;
      const durationMs = options.tracker?.takeDurationMs(toolCall.id);

      await options.sink.recordWorkerExecution({
        id: genId(),
        runId,
        taskId: details?.taskId ?? toolCall.id,
        capability: details?.capability ?? toolCall.name,
        workerType: details?.workerType ?? toolCall.name,
        attempt: details?.attempt ?? 0,
        status: isError ? 'failed' : (details?.status ?? 'success'),
        durationMs,
        feedbackType: details?.feedback && details.feedback.type !== 'none' ? details.feedback.type : undefined,
        errorCode: details?.error?.code,
        details: details ?? result,
      });

      const feedback = details?.feedback;
      if (feedback && feedback.type !== 'none') {
        await options.sink.appendEvent({
          id: genId(),
          runId,
          type: feedback.type,
          reason: feedback.reason,
          payload: {
            correlationId: toolCall.id,
            toolName: toolCall.name,
            affectedTaskIds: feedback.affectedTaskIds,
          },
        });
      }
    } catch (error) {
      handleError(error);
    }
    return undefined;
  };
}
