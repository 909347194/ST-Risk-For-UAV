// Planner Orchestrator — API → Plan/Run → Planner Agent（带三钩子）→ 收集 → 持久化。
// 替代旧 modules/agent/agent.service.ts 的 TODO 占位。
//
// 设计定调（见 agent-architecture-node-landing.md §13）：
//   - Replanner 只做预算/安全否决（maxTurns/超时/预算），正向决策归 Planner；
//   - 三钩子 = pi 原生 beforeToolCall / afterToolCall / finishTurn，不自研平行机制；
//   - 不信任 Planner 输出：最终方案须过 validation 硬闸门（Phase 1 接入）。

import { Injectable } from '@nestjs/common';

import { randomUUID } from 'node:crypto';
import type { AgentOptions } from '@earendil-works/pi-agent-core';
import type { Model, Models } from '@earendil-works/pi-ai';
import type { PlannerRunContext } from '@/agents/core/planner-context';
import { buildPlannerSystemPrompt } from '@/agents/planner/system-prompt';
import type { DispatchRepository } from '@/services/db/dispatch.repo';
import type { WorkerRouter } from '@/orchestration/worker-router';
import { createBeforeToolCallHook, EXECUTION_POLICY_DEFAULTS } from '@/orchestration/execution-policy';
import { createAfterToolCallHook, ToolExecutionTracker } from '@/orchestration/feedback-handler';
import { createFinishTurnHook } from '@/orchestration/replanner';

export interface DispatchIntent {
  /** 调度意图（人类语言）。 */
  objective: string;
  /** 约束（时间窗/区域/资源限制等）。 */
  constraints?: Record<string, unknown>;
}

export interface DispatchOutcome {
  planId: string;
  runId: string;
  status: string;
  message: string;
}

@Injectable()
export class PlannerOrchestrator {
  constructor(
    private readonly repo: DispatchRepository,
    private readonly router: WorkerRouter,
  ) {}

  /** 执行一次调度意图（骨架：Plan/Run 落库已通，LLM 闭环 Phase 1 接入）。 */
  async execute(intent: DispatchIntent): Promise<DispatchOutcome> {
    // ① Plan + Run 落库（真实状态，不再用内存 Map）
    const plan = await this.repo.createPlan({
      id: randomUUID(),
      objective: intent.objective,
      constraints: intent.constraints ?? {},
      status: 'planning',
    });
    const run = await this.repo.createRun({
      id: randomUUID(),
      planId: plan.id,
      status: 'planning',
    });

    const ctx: PlannerRunContext = {
      planId: plan.id,
      runId: run.id,
      attempt: 0,
      objective: intent.objective,
      maxTurns: EXECUTION_POLICY_DEFAULTS.maxTurns,
      timeoutMs: EXECUTION_POLICY_DEFAULTS.timeoutMs,
    };

    // ② 装配 pi 三钩子（Replanner 只做否决；策略常量统一取自 EXECUTION_POLICY_DEFAULTS）
    const tracker = new ToolExecutionTracker();
    const hooks: Pick<AgentOptions, 'beforeToolCall' | 'afterToolCall' | 'finishTurn'> = {
      beforeToolCall: createBeforeToolCallHook({
        tracker,
        maxCallsPerTool: EXECUTION_POLICY_DEFAULTS.maxCallsPerTool,
      }),
      afterToolCall: createAfterToolCallHook({
        runId: run.id,
        sink: this.repo, // DispatchRepository 结构化满足 DispatchRecordSink
        genId: randomUUID,
        tracker,
      }),
      finishTurn: createFinishTurnHook({ maxTurns: ctx.maxTurns }),
    };

    // ③ 装配 Planner Agent 并驱动
    // TODO Phase 1：createPlannerAgent({
    //   models, model, runContext: ctx, dispatch: this.router.dispatch,
    //   systemPrompt: buildPlannerSystemPrompt(ctx, this.router.listCapabilities()), ...hooks })
    //              → agent.prompt(intent.objective)
    //              → subscribe 事件流落库/SSE（§7.6）
    //              → Run 硬超时 ctx.timeoutMs → agent.abort() 降级人工
    //              → 最终方案过 validation 硬闸门后再置 COMPLETED
    void hooks;
    void buildPlannerSystemPrompt(ctx, this.router.listCapabilities());

    return {
      planId: plan.id,
      runId: run.id,
      status: 'planning',
      message: 'skeleton: Plan/Run 已落库，LLM 闭环待 Phase 1 接入',
    };
  }
}
