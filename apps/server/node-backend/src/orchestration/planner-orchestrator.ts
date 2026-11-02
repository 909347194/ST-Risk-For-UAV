// Planner Orchestrator — API → Plan/Run → Planner Agent（三钩子 + 事件流订阅）→ validation 硬闸门 → 持久化。
// 替代旧 modules/agent/agent.service.ts 的 TODO 占位（该模块已于 2026-10-28 拆除）。
//
// Phase 1 闭环（2026-10-19 落地，见 agent-architecture-node-landing.md §7.6/§13）：
//   createPlannerModel → createPlannerAgent → agent.prompt() → subscribe 事件流落库
//   + Run 硬超时（ctx.timeoutMs → agent.abort() → 降级人工接管）
//   + validation 硬闸门（最终方案过确定性校验才允许置 COMPLETED）
//
// 推流（2026-10-28 追加）：pi 无服务端推流原语，按 NestJS 主流方案 @Sse + RunEventBus 实现：
//   start() 非阻塞返回 runId → 前端打开 SSE（GET /dispatch/:runId/events）→ RunEventBus 回放+实时推送。
//   execute() 保持阻塞语义（测试/冒烟/CLI 场景），与 start() 共享同一条 runAndSettle → runLoop 主路径。
//
// 设计定调：
//   - Replanner 只做预算/安全否决（maxTurns/超时/预算），正向决策归 Planner；
//   - 三钩子 = pi 原生 beforeToolCall / afterToolCall / finishTurn，不自研平行机制；
//   - 不信任 Planner 输出：最终方案须过 validation 硬闸门（§13「四样兑底」之一）。

import { Injectable } from '@nestjs/common';

import { randomUUID } from 'node:crypto';
import type { AgentEvent, AgentOptions } from '@earendil-works/pi-agent-core';
import type { PlannerRunContext } from '@/agents/core/planner-context';
import { createPlannerAgent } from '@/agents/planner/planner.agent';
import { buildPlannerSystemPrompt } from '@/agents/planner/system-prompt';
import type { DispatchRepository } from '@/services/db/dispatch.repo';
import type { WorkerRouter } from '@/orchestration/worker-router';
import { createBeforeToolCallHook, EXECUTION_POLICY_DEFAULTS } from '@/orchestration/execution-policy';
import { createAfterToolCallHook, ToolExecutionTracker } from '@/orchestration/feedback-handler';
import { createFinishTurnHook } from '@/orchestration/replanner';
import { createPlannerModel, type PlannerModelHandle } from '@/infrastructure/llm/llm-config';
import { extractFinalPlan, validateFinalPlan, type ToolCallRecord } from '@/orchestration/validation-gate';
import { RunEventBus } from '@/orchestration/run-event-bus';
import type { WorkerResult } from '@/contracts/worker-result';

export interface DispatchIntent {
  /** 调度意图（人类语言）。 */
  objective: string;
  /** 约束（时间窗/区域/资源限制等）。 */
  constraints?: Record<string, unknown>;
  /** Run 硬超时预算（毫秒）；缺省取 EXECUTION_POLICY_DEFAULTS.timeoutMs。 */
  timeoutMs?: number;
}

export interface DispatchOutcome {
  planId: string;
  runId: string;
  status: string;
  message: string;
}

/** start() 的即时回执（闭环在后台跑，进度经 SSE 推送）。 */
export interface DispatchReceipt {
  planId: string;
  runId: string;
}

/** 推流转发、跳过的高频噪声事件（token 级增量/工具中间态）。 */
const SSE_SKIP_EVENTS = new Set<AgentEvent['type']>(['message_update', 'tool_execution_update']);

@Injectable()
export class PlannerOrchestrator {
  /**
   * LLM 装配工厂。默认 createPlannerModel（真实 DeepSeek，鉴权经 DEEPSEEK_API_KEY）；
   * 测试可覆盖为 faux provider 工厂，实现离线闭环回放（不触网、不连 DB）。
   */
  createModelHandle: () => Promise<PlannerModelHandle> = createPlannerModel;

  constructor(
    private readonly repo: DispatchRepository,
    private readonly router: WorkerRouter,
    private readonly bus: RunEventBus,
  ) {}

  /**
   * 非阻塞执行：创建 Plan+Run 后立即返回，闭环在后台驱动（SSE 推流给前端）。
   * 供 HTTP API 使用——前端拿 runId 订阅 GET /dispatch/:runId/events。
   */
  async start(intent: DispatchIntent): Promise<DispatchReceipt> {
    const { planId, runId, ctx } = await this.createPlanAndRun(intent);
    void this.runAndSettle(intent, planId, runId, ctx).catch((error) => {
      // runAndSettle 内部已兜底终态；此处仅防 DB 故障等意外逃逸。
      console.error('[planner-orchestrator] background run crashed:', error);
    });
    return { planId, runId };
  }

  /** 阻塞执行：驱动闭环到终态后返回结果（测试/冒烟/CLI 场景；与 start() 共享主路径）。 */
  async execute(intent: DispatchIntent): Promise<DispatchOutcome> {
    const { planId, runId, ctx } = await this.createPlanAndRun(intent);
    return this.runAndSettle(intent, planId, runId, ctx);
  }

  /** ① Plan + Run 落库（真实状态，不用内存 Map），装配 Run 上下文。 */
  private async createPlanAndRun(intent: DispatchIntent): Promise<{
    planId: string;
    runId: string;
    ctx: PlannerRunContext;
  }> {
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
      timeoutMs: intent.timeoutMs ?? EXECUTION_POLICY_DEFAULTS.timeoutMs,
    };
    return { planId: plan.id, runId: run.id, ctx };
  }

  /** run 生命周期包装：run_start / run_end 推流 + 意外崩溃兜底（终态必须可达，SSE 不能挂住）。 */
  private async runAndSettle(
    intent: DispatchIntent,
    planId: string,
    runId: string,
    ctx: PlannerRunContext,
  ): Promise<DispatchOutcome> {
    this.bus.publish(runId, { type: 'run_start', data: { planId, objective: intent.objective } });
    try {
      const outcome = await this.runLoop(intent, planId, runId, ctx);
      this.bus.publish(runId, { type: 'run_end', data: outcome });
      return outcome;
    } catch (error) {
      const outcome = await this.finalizeFailure(planId, runId, 'loop_crashed', error);
      this.bus.publish(runId, { type: 'run_end', data: outcome });
      return outcome;
    }
  }

  /** 闭环主路径：装配 Agent → prompt → 事件流落库/推流 → validation 硬闸门 → 终态。 */
  private async runLoop(
    intent: DispatchIntent,
    planId: string,
    runId: string,
    ctx: PlannerRunContext,
  ): Promise<DispatchOutcome> {
    // ② 装配 pi 三钩子（策略常量统一取自 EXECUTION_POLICY_DEFAULTS）。
    //    afterToolCall 在基础落库之外收集 (args, result)，供 validation 闸门提取最终方案。
    const tracker = new ToolExecutionTracker();
    const toolRecords: ToolCallRecord[] = [];
    const baseAfterToolCall = createAfterToolCallHook({
      runId,
      sink: this.repo, // DispatchRepository 结构化满足 DispatchRecordSink
      genId: randomUUID,
      tracker,
    });
    const hooks: Pick<AgentOptions, 'beforeToolCall' | 'afterToolCall' | 'finishTurn'> = {
      beforeToolCall: createBeforeToolCallHook({
        tracker,
        maxCallsPerTool: EXECUTION_POLICY_DEFAULTS.maxCallsPerTool,
      }),
      afterToolCall: async (context, signal) => {
        const outcome = await baseAfterToolCall(context, signal);
        const details = context.result?.details as WorkerResult | undefined;
        if (details) {
          toolRecords.push({ toolName: context.toolCall.name, args: context.args, result: details });
        }
        return outcome;
      },
      finishTurn: createFinishTurnHook({ maxTurns: ctx.maxTurns }),
    };

    // ③ 装配 Planner Agent（LLM 闭环入口：createPlannerModel → createPlannerAgent）
    let agent: Awaited<ReturnType<typeof createPlannerAgent>>;
    try {
      const { models, model } = await this.createModelHandle();
      agent = await createPlannerAgent({
        models,
        model,
        systemPrompt: buildPlannerSystemPrompt(ctx, this.router.listCapabilities()),
        runContext: ctx,
        dispatch: this.router.dispatch,
        ...hooks,
      });
    } catch (error) {
      return this.finalizeFailure(planId, runId, 'llm_unavailable', error);
    }

    // ④ 事件流订阅 → 落库 + 推流（§7.6：agent_start → runs.status；turn_start/turn_end → dispatch_events；
    //    全量事件（除 token 级噪声）经 RunEventBus fan-out 给 SSE 订阅者）。
    //    listener 按注册序被 await，属 run settlement 一部分——落库在此有"已持久化"保证。
    const unsubscribe = agent.subscribe(async (event) => {
      try {
        if (event.type === 'agent_start') {
          await this.repo.updateRunStatus(runId, 'executing');
        } else if (event.type === 'turn_start') {
          await this.repo.appendEvent({
            id: randomUUID(),
            runId,
            type: 'turn_start',
            payload: { planId },
          });
        } else if (event.type === 'turn_end') {
          await this.repo.appendEvent({
            id: randomUUID(),
            runId,
            type: 'turn_end',
            // turn_end 的 message 运行时恒为 AssistantMessage（联合类型收窄）
            payload: { stopReason: (event.message as { stopReason?: string }).stopReason },
          });
        }
        if (!SSE_SKIP_EVENTS.has(event.type)) {
          this.bus.publish(runId, { type: event.type, data: this.toStreamPayload(event) });
        }
      } catch (error) {
        // 事件落库失败不打断 Agent 运行（与 feedback-handler 的 onError 约定一致）。
        console.error('[planner-orchestrator] event persist failed:', error);
      }
    });

    // ⑤ Run 硬超时：到点 agent.abort() → 流式中断（stopReason=aborted）→ prompt 收敛 → 降级人工。
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      agent.abort();
    }, ctx.timeoutMs);
    try {
      await agent.prompt(intent.objective);
    } catch (error) {
      // prompt 内部已吞掉 abort/stream 错误（handleRunFailure）；走到这里是非预期异常。
      clearTimeout(timer);
      unsubscribe();
      return this.finalizeFailure(planId, runId, 'prompt_failed', error);
    }
    clearTimeout(timer);
    await agent.waitForIdle();
    unsubscribe();

    if (timedOut) {
      return this.finalizeFailure(
        planId,
        runId,
        'run_timeout',
        new Error(`Run 硬超时（${ctx.timeoutMs}ms），已降级人工接管`),
      );
    }

    // ⑥ validation 硬闸门：不信任 Planner 输出，最终方案必须过确定性校验。
    const candidate = extractFinalPlan(toolRecords);
    if (!candidate) {
      return this.finalizeFailure(
        planId,
        runId,
        'no_plan',
        new Error('Planner 未产出可用分配方案（无成功的 assign_tasks 调用）'),
      );
    }
    await this.repo.updateRunStatus(runId, 'validating');
    const validation = validateFinalPlan(candidate);
    if (!validation.valid) {
      await this.repo.finalizeRun(runId, {
        status: 'failed',
        payload: {
          reason: 'validation_rejected',
          violations: validation.violations,
          transcript: this.snapshotTranscript(agent),
        },
      });
      return {
        planId,
        runId,
        status: 'failed',
        message: `validation 硬闸门拦截：${validation.violations.join('；')}`,
      };
    }

    await this.repo.finalizeRun(runId, {
      status: 'completed',
      payload: { plan: candidate.plan, transcript: this.snapshotTranscript(agent) },
    });
    return {
      planId,
      runId,
      status: 'completed',
      message: `调度完成：${candidate.plan.allocations.length} 项分配，${candidate.plan.unassigned_tasks.length} 项未分配`,
    };
  }

  /** AgentEvent → 推流载荷（裁剪体积：agent_end 不带全量 messages，体积大的留给 DB 转录）。 */
  private toStreamPayload(event: AgentEvent): unknown {
    switch (event.type) {
      case 'agent_end':
        return { messageCount: event.messages.length };
      case 'turn_end':
        return { stopReason: (event.message as { stopReason?: string }).stopReason };
      case 'tool_execution_start':
        return { toolCallId: event.toolCallId, toolName: event.toolName, args: event.args };
      case 'tool_execution_end':
        return {
          toolCallId: event.toolCallId,
          toolName: event.toolName,
          result: event.result,
          isError: event.isError,
        };
      case 'message_end':
        return { message: event.message };
      default:
        return {};
    }
  }

  /** 转录快照（Phase 1 简化：agent.state.messages 序列化进 runs.payload，见 §7.7）。 */
  private snapshotTranscript(agent: Awaited<ReturnType<typeof createPlannerAgent>>): unknown {
    try {
      return agent.state.messages;
    } catch {
      return undefined;
    }
  }

  /** 失败统一出口：终态落库 + 返回（含原因，供人工接管排查）。 */
  private async finalizeFailure(
    planId: string,
    runId: string,
    reason: string,
    error: unknown,
  ): Promise<DispatchOutcome> {
    await this.repo.finalizeRun(runId, {
      status: 'failed',
      payload: { reason, error: error instanceof Error ? error.message : String(error) },
    });
    return {
      planId,
      runId,
      status: 'failed',
      message: `${reason}: ${error instanceof Error ? error.message : String(error)}`,
    };
  }
}
