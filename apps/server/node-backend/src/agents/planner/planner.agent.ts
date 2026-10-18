// Planner Agent 参考实现 — 证明约束 2（ESM 惰性加载）与约束 3（TypeBox 工具）在当前
// CommonJS 工程中可正常编译与装配。它不作为运行时入口；真正的编排在 orchestration/planner-orchestrator。
//
// 关键点：
//  - 所有 pi-agent-core / pi-ai 的"运行时值"都通过 loadPiRuntime() 动态取出，杜绝静态 ESM import。
//  - 工具参数用 TypeBox（见 tools/assign-tasks.tool.ts），pi 运行时自动按 schema 校验工具参数。
//  - 工具 execute 只构造 WorkerTask 并调用注入的 dispatch（Router），不直接持有 Worker 实现。
//  - 工具失败 throw（pi 约定，见 workerResultToToolResult）；Worker id 用 pi 的 uuidv7。
//  - Agent 构造：systemPrompt / model / tools 都在 initialState 里（pi 契约，model 必给，否则跑不了一轮）。
//  - Replanner/Feedback/执行策略不是自研框架，而是 pi 的 finishTurn/afterToolCall/beforeToolCall 钩子，
//    由 orchestration 层工厂构造后注入（见 orchestration/replanner|feedback-handler|execution-policy）。

import type { AgentOptions } from '@earendil-works/pi-agent-core';
import type { Model, Models } from '@earendil-works/pi-ai';
import { createStreamFn, loadPiRuntime } from '@/agents/core/runtime-loader';
import { createAssignTasksTool } from '@/agents/planner/tools/assign-tasks.tool';
import type { DispatchFn } from '@/orchestration/worker-router';

export type { DispatchFn };

export interface CreatePlannerAgentOptions {
  /** pi-ai 的 Models 实例（已配置凭证/provider）。 */
  models: Models;
  /**
   * pi-ai 的 Model 对象（`models.getModel(provider, id)` 取得）。
   * 必填：AgentState.model 是每轮请求必用的模型，缺失则无法真正跑一轮。
   */
  model: Model<any>;
  /** 系统提示词。 */
  systemPrompt: string;
  /** Worker 委派入口。 */
  dispatch: DispatchFn;
  /**
   * pi 钩子（可选）：由 orchestration 层工厂构造后注入，
   * 即 createBeforeToolCallHook / createAfterToolCallHook / createFinishTurnHook 的产物。
   */
  beforeToolCall?: AgentOptions['beforeToolCall'];
  afterToolCall?: AgentOptions['afterToolCall'];
  finishTurn?: AgentOptions['finishTurn'];
}

/**
 * 构造 Planner Agent 实例。
 * 返回 Agent（stateful），调用方通过 `agent.prompt(...)` 驱动一次调度认知。
 */
export async function createPlannerAgent(options: CreatePlannerAgentOptions) {
  const { ai, core } = await loadPiRuntime();

  // ① Planner 工具：委派"任务分配"能力（薄按钮，参数 TypeBox、失败 throw、派发串行）。
  const assignTasksTool = createAssignTasksTool(ai, options.dispatch);

  // ② 构造 Agent：streamFn 由 pi-ai 的 Models 实例提供；systemPrompt / model / tools 都在 initialState（pi 契约）。
  //    Replanner/Feedback/执行策略以 pi 钩子注入（undefined 即不启用，不自研平行机制）。
  const agent = new core.Agent({
    streamFn: createStreamFn(options.models),
    initialState: {
      systemPrompt: options.systemPrompt,
      model: options.model,
      tools: [assignTasksTool],
    },
    beforeToolCall: options.beforeToolCall,
    afterToolCall: options.afterToolCall,
    finishTurn: options.finishTurn,
  });

  return agent;
}
