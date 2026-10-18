// Planner 工具工厂 — 落实 "AgentTool.parameters 必须用 TypeBox，不是 zod" 的约束。
//
// pi-agent-core 的 `AgentTool<TParameters extends TSchema>` 要求 TypeBox schema（来自 pi-ai 的 Type）。
// 注意：
//  - `parameters` 是给 LLM 看的工具参数声明，必须用 TypeBox（`Type.Object({...})`）。
//  - zod 只用于 Nest 控制器 DTO 校验，以及 Contract 边界的"运行期校验"（见 contracts/runtime-schema）。
//  - 本文件只用 `import type`，不引入任何运行时 ESM 符号；`Type` 由调用方从 runtime-loader 取得。

import type { AgentTool, AgentToolResult } from '@earendil-works/pi-agent-core';
import type { Static, TSchema } from '@earendil-works/pi-ai';

export interface PlannerToolConfig<TParams extends TSchema> {
  /** 工具名（模型调用时使用的 name）。 */
  name: string;
  /** 人类可读标签（UI 展示）。 */
  label: string;
  /** 工具用途描述（给模型）。 */
  description: string;
  /** TypeBox 参数 schema（已由调用方用 Type.* 构造好）。 */
  parameters: TParams;
  /**
   * 执行函数：把模型参数包成 WorkerTask 并委派给 WorkerRouter。
   * 不在此直接 new Worker，只负责构造任务 + 调用 dispatch。
   */
  execute: (
    toolCallId: string,
    params: Static<TParams>,
    signal?: AbortSignal,
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
    execute: config.execute,
  };
}

/** 把任意结构化结果包成 AgentToolResult（供工具 execute 直接返回）。 */
export function toAgentToolResult<T>(result: T): AgentToolResult<T> {
  return {
    content: [{ type: 'text', text: JSON.stringify(result) }],
    details: result,
  };
}
