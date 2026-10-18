// Planner 工具：任务分配 — 委派 capability `allocation.assign`（薄按钮，不是通信代码）。
// 约定（pi）：参数 TypeBox；失败 throw（workerResultToToolResult）；派发有副作用 → sequential + replay:'never'。

import type { AgentTool } from '@earendil-works/pi-agent-core';
import { definePlannerTool, workerResultToToolResult } from '@/agents/core/planner-tool';
import type { PiAi } from '@/agents/core/runtime-loader';
import type { DispatchFn } from '@/orchestration/worker-router';
import type { WorkerTask } from '@/contracts/worker-task';
import { WORKER_CONTRACT_VERSION } from '@/contracts/version';

/**
 * 构造 assign_tasks 工具。
 * @param ai pi-ai 命名空间（取 Type / uuidv7 运行时值；经 runtime-loader 动态加载后传入）
 */
export function createAssignTasksTool(
  ai: Pick<PiAi, 'Type' | 'uuidv7'>,
  dispatch: DispatchFn,
): AgentTool<any> {
  const { Type } = ai;

  return definePlannerTool({
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
      const result = await dispatch('allocation.assign', task);
      // failed → throw；need_input → terminate:true；其余正常返回（回填 correlationId）。
      return workerResultToToolResult(result, toolCallId);
    },
  });
}
