// Planner 工具工厂 — 落实 "AgentTool.parameters 必须用 TypeBox，不是 zod" 的约束。
//
// pi-agent-core 的 `AgentTool<TParameters extends TSchema>` 要求 TypeBox schema（来自 pi-ai 的 Type）。
// 注意：
//  - `parameters` 是给 LLM 看的工具参数声明，必须用 TypeBox（`Type.Object({...})`）；pi 运行时会自动按其校验参数。
//  - zod 只用于 Nest 控制器 DTO 校验，以及 Contract 边界的"运行期校验"（见 contracts/runtime-schema）。
//  - **失败必须 throw（pi 约定）**：运行时会以 isError:true 把错误报告给模型，由模型自纠/重试；不要把错误包进 content。
//  - 有副作用的派发工具设 executionMode: 'sequential'（整批退化串行）；派发类工具建议 replay: 'never'。
//  - 本文件只用 `import type`，不引入任何运行时 ESM 符号；`Type` 由调用方从 runtime-loader 取得。

import type { AgentTool, AgentToolResult, AgentToolUpdateCallback } from '@earendil-works/pi-agent-core';
import type { Static, TSchema } from '@earendil-works/pi-ai';
import type { WorkerResult } from '@/contracts/worker-result';

export interface PlannerToolConfig<TParams extends TSchema> {
  /** 工具名（模型调用时使用的 name）。 */
  name: string;
  /** 人类可读标签（UI 展示；pi 契约里 `label` 是必填字段）。 */
  label: string;
  /** 工具用途描述（给模型）。 */
  description: string;
  /** TypeBox 参数 schema（已由调用方用 Type.* 构造好）。 */
  parameters: TParams;
  /**
   * 执行模式（pi 的 `AgentTool.executionMode`）：
   * - 'sequential'：有副作用（派发/写库）的工具，整批工具调用退化为串行执行。
   * - 'parallel'：纯查询类工具，可与其他工具调用并发。
   * 不填则跟随 Agent 全局 `toolExecution` 配置（默认 parallel）。
   */
  executionMode?: 'sequential' | 'parallel';
  /** 副作用重放策略（pi 的 `AgentTool.replay`）：派发类工具用 'never'。 */
  replay?: 'never' | 'safe';
  /**
   * 执行函数：把模型参数包成 WorkerTask 并委派给 WorkerRouter。
   * 不在此直接 new Worker，只负责构造任务 + 调用 dispatch。
   * **失败请 throw**（pi 约定），不要返回错误内容；`onUpdate` 可回传长耗时调用的中间进度。
   */
  execute: (
    toolCallId: string,
    params: Static<TParams>,
    signal?: AbortSignal,
    onUpdate?: AgentToolUpdateCallback<any>,
  ) => Promise<AgentToolResult<any>>;
}

/**
 * 构造一个类型安全的 Planner 工具（AgentTool）。
 * 统一封装 AgentToolResult 的结构，避免各处重复 content/details 写法。
 */
export function definePlannerTool<TParams extends TSchema>(
  config: PlannerToolConfig<TParams>,
): AgentTool<TParams> {
  return {
    name: config.name,
    label: config.label,
    description: config.description,
    parameters: config.parameters,
    ...(config.executionMode ? { executionMode: config.executionMode } : {}),
    ...(config.replay ? { replay: config.replay } : {}),
    execute: config.execute,
  };
}

/** 把任意结构化结果包成 AgentToolResult（供工具 execute 在成功路径直接返回）。 */
export function toAgentToolResult<T>(result: T): AgentToolResult<T> {
  return {
    content: [{ type: 'text', text: JSON.stringify(result) }],
    details: result,
  };
}

/**
 * 把 WorkerResult 转成 AgentToolResult —— 遵循 pi 的工具结果约定：
 * - `failed`    → **throw**（运行时以 isError:true 交还模型自纠/重试，不要把错误包成成功内容）
 * - `need_input` → 返回 `terminate: true`（提示停轮；注意 pi 语义是"整批工具结果全 terminate 才提前停轮"）
 * - `success` / `partial` → 正常返回 content + details
 *
 * `correlationId`（pi 的 toolCallId）会回填到 details，供 afterToolCall 落库时串联
 *「工具调用 ↔ WorkerTask ↔ worker_executions」三方记录。
 */
export function workerResultToToolResult(
  result: WorkerResult,
  correlationId?: string,
): AgentToolResult<WorkerResult> {
  if (result.status === 'failed') {
    const code = result.error?.code ?? 'WORKER_FAILED';
    const message = result.error?.message ?? 'worker execution failed';
    throw new Error(`[${result.workerType}] ${code}: ${message}`);
  }
  const details: WorkerResult = {
    ...result,
    correlationId: result.correlationId ?? correlationId,
  };
  return {
    content: [{ type: 'text', text: JSON.stringify(details.result ?? null) }],
    details,
    terminate: details.status === 'need_input' ? true : undefined,
  };
}
