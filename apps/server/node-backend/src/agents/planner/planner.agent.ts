// Planner Agent 参考实现 — 证明约束 2（ESM 惰性加载）与约束 3（TypeBox 工具）在当前
// CommonJS 工程中可正常编译与装配。它不作为运行时入口；真正的编排在 orchestration/planner-orchestrator。
//
// 关键点：
//  - 所有 pi-agent-core / pi-ai 的"运行时值"都通过 loadPiRuntime() 动态取出，杜绝静态 ESM import。
//  - 工具参数用 TypeBox（ai.Type.Object），不是 zod。
//  - 工具 execute 只构造 WorkerTask 并调用注入的 dispatch（Router），不直接持有 Worker 实现。

import { randomUUID } from 'node:crypto';

import { WORKER_CONTRACT_VERSION } from '@/contracts/version';
import type { WorkerTask } from '@/contracts/worker-task';
import type { WorkerResult } from '@/contracts/worker-result';
import { definePlannerTool, toAgentToolResult } from '@/agents/core/planner-tool';
import { createStreamFn, loadPiRuntime } from '@/agents/core/runtime-loader';
import type { Models } from '@earendil-works/pi-ai';

/** Planner 委派 Worker 的入口（由 WorkerRouter 注入）。 */
export type DispatchFn = (capability: string, task: WorkerTask) => Promise<WorkerResult>;

export interface CreatePlannerAgentOptions {
  /** pi-ai 的 Models 实例（已配置凭证/provider）。 */
  models: Models;
  /** 系统提示词。 */
  systemPrompt: string;
  /** Worker 委派入口。 */
  dispatch: DispatchFn;
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
    }),
    execute: async (_toolCallId, params) => {
      const task: WorkerTask = {
        taskId: randomUUID(),
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
      return toAgentToolResult(result);
    },
  });

  // ② 构造 Agent：streamFn 由 pi-ai 的 Models 实例提供。
  const { core } = await loadPiRuntime();
  const agent = new core.Agent({
    streamFn: createStreamFn(options.models),
    initialState: { systemPrompt: options.systemPrompt, tools: [assignTasksTool] },
  });

  return agent;
}
