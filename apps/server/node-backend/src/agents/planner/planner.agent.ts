// Planner Agent 参考实现 — 证明约束 2（ESM 惰性加载）与约束 3（TypeBox 工具）在当前
// CommonJS 工程中可正常编译与装配。它不作为运行时入口；真正的编排在 orchestration/planner-orchestrator。
//
// 关键点：
//  - 所有 pi-agent-core / pi-ai 的"运行时值"都通过 loadPiRuntime() 动态取出，杜绝静态 ESM import。
//  - 工具参数用 TypeBox（ai.Type.Object），不是 zod；pi 运行时自动按 schema 校验工具参数。
//  - 工具 execute 只构造 WorkerTask 并调用注入的 dispatch（Router），不直接持有 Worker 实现。
//  - 工具失败 throw（pi 约定，见 workerResultToToolResult）；Worker id 用 pi 的 uuidv7。
//  - Agent 构造：systemPrompt / model / tools 都在 initialState 里（pi 契约，model 必给，否则跑不了一轮）。
//  - Replanner/Feedback/执行策略不是自研框架，而是 pi 的 finishTurn/afterToolCall/beforeToolCall 钩子，
//    由 orchestration 层工厂构造后注入（见 orchestration/replanner|feedback-handler|execution-policy）。

import { WORKER_CONTRACT_VERSION } from '@/contracts/version';
import type { WorkerTask } from '@/contracts/worker-task';
import type { WorkerResult } from '@/contracts/worker-result';
import { definePlannerTool, workerResultToToolResult } from '@/agents/core/planner-tool';
import { createStreamFn, loadPiRuntime } from '@/agents/core/runtime-loader';
import type { AgentOptions } from '@earendil-works/pi-agent-core';
import type { Model, Models } from '@earendil-works/pi-ai';

/** Planner 委派 Worker 的入口（由 WorkerRouter 注入）。 */
export type DispatchFn = (capability: string, task: WorkerTask) => Promise<WorkerResult>;

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
  const { ai } = await loadPiRuntime();
  const { Type } = ai;

  // ① Planner 工具：委派"任务分配"能力。参数用 TypeBox。
  const assignTasksTool = definePlannerTool({
    name: 'assign_tasks',
    label: '任务分配',
    description: '将任务分配给可用无人机，返回分配方案。调用 allocation.assign 能力。',
    parameters: Type.Object({
      uavIds: Type.Array(Type.String()),
      taskIds: Type.Array(Type.String()),
      algorithm: Type.Optional(Type.String()),
    }, { additionalProperties: false }),
    // 派发有副作用（写库/触发算法服务）→ 整批串行，且不可重放。
    executionMode: 'sequential',
    replay: 'never',
    execute: async (toolCallId, params) => {
      const task: WorkerTask = {
        taskId: ai.uuidv7(), // pi 约定：时间有序 ID
        correlationId: toolCallId, // pi 的 toolCallId，供 afterToolCall 落库三方关联
        planId: '',
        runId: '',
        workerType: 'allocation-worker',
        capability: 'allocation.assign',
        objective: 'assign tasks to uavs',
        input: params,
        attempt: 0,
        schemaVersion: WORKER_CONTRACT_VERSION,
      };
      const result = await options.dispatch('allocation.assign', task);
      // failed → throw；need_input → terminate:true；其余正常返回（回填 correlationId）。
      return workerResultToToolResult(result, toolCallId);
    },
  });

  // ② 构造 Agent：streamFn 由 pi-ai 的 Models 实例提供；systemPrompt / model / tools 都在 initialState（pi 契约）。
  //    Replanner/Feedback/执行策略以 pi 钩子注入（undefined 即不启用，不自研平行机制）。
  const { core } = await loadPiRuntime();
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
