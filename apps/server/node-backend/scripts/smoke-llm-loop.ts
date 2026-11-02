#!/usr/bin/env node
/**
 * LLM 闭环冒烟脚本（真实 DeepSeek API）— 验证用户指定链路在真实模型下跑通：
 *   createPlannerModel → createPlannerAgent → prompt → 事件流落库 → validation 硬闸门
 *
 * 前置：仓库根 .env 已配置 DEEPSEEK_API_KEY（pi 的 DeepSeek provider 经 envApiKeyAuth 读取）。
 * 运行（在 apps/server/node-backend 目录下）：
 *   node -r ts-node/register/transpile-only -r tsconfig-paths/register scripts/smoke-llm-loop.ts
 *
 * 不起 Python 后端 / 不连 PostgreSQL：Worker 用内存替身（按工具入参生成一致方案），
 * DB 用内存 repo（打印落库过程）。真实 DB 落库验证请在 PostgreSQL 就绪后自行运行。
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

// ── .env 加载（无 dotenv 依赖；不覆盖已存在的环境变量）──
function loadEnvFile(file: string): void {
  const content = readFileSync(file, 'utf-8');
  for (const line of content.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eq = trimmed.indexOf('=');
    if (eq === -1) continue;
    const key = trimmed.slice(0, eq).trim();
    const value = trimmed.slice(eq + 1).trim();
    if (key && !(key in process.env)) process.env[key] = value;
  }
}

loadEnvFile(resolve(__dirname, '../../../../.env'));

import type { AgentMessage } from '@earendil-works/pi-agent-core';
import { createPlannerModel } from '../src/infrastructure/llm/llm-config';
import { createPlannerAgent } from '../src/agents/planner/planner.agent';
import { buildPlannerSystemPrompt } from '../src/agents/planner/system-prompt';
import { WorkerRegistry } from '../src/registry/worker-registry';
import { WorkerRouter } from '../src/orchestration/worker-router';
import { PlannerOrchestrator } from '../src/orchestration/planner-orchestrator';
import { RunEventBus } from '../src/orchestration/run-event-bus';
import { EXECUTION_POLICY_DEFAULTS } from '../src/orchestration/execution-policy';
import type { PlannerRunContext } from '../src/agents/core/planner-context';
import type { WorkerDefinition } from '../src/agents/core/worker-runtime.interface';
import type { WorkerResult } from '../src/contracts/worker-result';
import type { WorkerTask } from '../src/contracts/worker-task';
import type { DispatchRepository } from '../src/services/db/dispatch.repo';
import type { NewDispatchEvent, NewPlan, NewRun, NewWorkerExecution } from '../src/db/models';

const OBJECTIVE =
  'XX 区域火灾侦察：可用无人机 uav-1、uav-2，待分配任务 task-1、task-2。' +
  '请调用 assign_tasks 工具完成分配（uavIds/taskIds 用上述 ID），并在工具返回后给出最终方案摘要。';

// ── 内存 Worker：按工具入参生成一致方案（round-robin），不起 Python ──
function memoryAllocationDefinition(): WorkerDefinition {
  return {
    capability: 'allocation.assign',
    workerType: 'allocation-worker',
    description: '内存替身 allocation worker（冒烟脚本用，不调 Python）',
    runtimeFactory: () => ({
      run: async (task: WorkerTask): Promise<WorkerResult> => {
        const input = task.input as { uavIds: string[]; taskIds: string[] };
        const allocations = input.taskIds.map((taskId, i) => ({
          uav_id: input.uavIds[i % input.uavIds.length],
          task_id: taskId,
          estimated_cost: 10 + i,
        }));
        return {
          taskId: task.taskId,
          correlationId: task.correlationId,
          planId: task.planId,
          runId: task.runId,
          workerType: 'allocation-worker',
          capability: 'allocation.assign',
          attempt: task.attempt,
          status: 'success',
          result: { allocations, unassigned_tasks: [], algorithm_used: 'hungarian' },
        };
      },
    }),
  };
}

// ── 内存 repo：打印落库过程（结构化满足 DispatchRepository 子集）──
class MemoryRepo {
  readonly runs: NewRun[] = [];
  readonly workerExecutions: NewWorkerExecution[] = [];
  readonly events: NewDispatchEvent[] = [];

  async createPlan(input: NewPlan): Promise<NewPlan> {
    return input;
  }
  async createRun(input: NewRun): Promise<NewRun> {
    this.runs.push(input);
    console.log(`      [落库] runs ← status=${input.status}`);
    return input;
  }
  async updateRunStatus(id: string, status: string): Promise<void> {
    const run = this.runs.find((r) => r.id === id);
    if (run) {
      run.status = status;
      console.log(`      [落库] runs.status ← ${status}`);
    }
  }
  async finalizeRun(id: string, input: { status: string; payload?: unknown }): Promise<void> {
    const run = this.runs.find((r) => r.id === id);
    if (run) {
      run.status = input.status;
      run.payload = input.payload;
      console.log(`      [落库] runs 终态 ← ${input.status}`);
    }
  }
  async recordWorkerExecution(input: NewWorkerExecution): Promise<NewWorkerExecution> {
    this.workerExecutions.push(input);
    console.log(`      [落库] worker_executions ← ${input.capability} status=${input.status}`);
    return input;
  }
  async listWorkerExecutions(runId: string): Promise<NewWorkerExecution[]> {
    return this.workerExecutions.filter((e) => e.runId === runId);
  }
  async appendEvent(input: NewDispatchEvent): Promise<void> {
    this.events.push(input);
    console.log(`      [落库] dispatch_events ← ${input.type}`);
  }
}

function assistantText(message: AgentMessage): string {
  if (message.role !== 'assistant') return '';
  return message.content
    .filter((block) => block.type === 'text')
    .map((block) => block.text)
    .join('');
}

async function main(): Promise<void> {
  if (!process.env.DEEPSEEK_API_KEY) {
    console.error('缺少 DEEPSEEK_API_KEY（请在仓库根 .env 配置）');
    process.exit(1);
  }

  // ① 真实模型装配（鉴权预检 + pi 模型目录）
  console.log('[1/4] createPlannerModel（真实 DeepSeek）...');
  const { models, model } = await createPlannerModel();
  console.log(`      provider=${model.provider} model=${model.id}`);

  const registry = new WorkerRegistry();
  registry.register(memoryAllocationDefinition());
  const router = new WorkerRouter(registry);

  // ② 手动链路：createPlannerAgent → subscribe（打印事件流）→ prompt
  console.log('[2/4] createPlannerAgent + 事件流订阅...');
  const ctx: PlannerRunContext = {
    planId: 'smoke-plan',
    runId: 'smoke-run',
    attempt: 0,
    objective: OBJECTIVE,
    maxTurns: EXECUTION_POLICY_DEFAULTS.maxTurns,
    timeoutMs: EXECUTION_POLICY_DEFAULTS.timeoutMs,
  };
  const agent = await createPlannerAgent({
    models,
    model,
    systemPrompt: buildPlannerSystemPrompt(ctx, router.listCapabilities()),
    runContext: ctx,
    dispatch: router.dispatch,
  });

  const eventTypes: string[] = [];
  agent.subscribe((event) => {
    eventTypes.push(event.type);
    if (event.type === 'tool_execution_start') {
      console.log(`      → tool_execution_start: ${event.toolName}`);
    } else if (event.type === 'tool_execution_end') {
      console.log(`      → tool_execution_end: ${event.toolName} isError=${event.isError}`);
    } else if (event.type === 'message_end' && event.message.role === 'assistant') {
      const text = assistantText(event.message);
      if (text) console.log(`      ← assistant: ${text.slice(0, 100)}`);
    }
  });

  console.log('[3/4] agent.prompt(...) 驱动真实 LLM...');
  const started = Date.now();
  await agent.prompt(OBJECTIVE);
  console.log(`      prompt 收敛，耗时 ${Date.now() - started}ms`);
  console.log(`      事件流: ${eventTypes.join(' → ')}`);

  // ③ 完整编排路径（内存 repo）：事件流落库 + validation 硬闸门
  console.log('[4/4] PlannerOrchestrator 全链路（内存 repo 落库）...');
  const repo = new MemoryRepo();
  const bus = new RunEventBus();
  const orchestrator = new PlannerOrchestrator(repo as unknown as DispatchRepository, router, bus);
  const outcome = await orchestrator.execute({ objective: OBJECTIVE });
  console.log(`      outcome: status=${outcome.status}`);
  console.log(`      message: ${outcome.message}`);
  console.log(`      worker_executions: ${repo.workerExecutions.length} 条`);
  console.log(`      dispatch_events: ${repo.events.map((e) => e.type).join(', ')}`);

  const ok = outcome.status === 'completed';
  console.log(
    ok
      ? '\n✅ 冒烟通过：createPlannerModel → createPlannerAgent → prompt → 事件流落库 → validation 硬闸门，真实模型下全链路跑通'
      : '\n❌ 冒烟未通过（见上方 outcome）',
  );
  process.exit(ok ? 0 : 1);
}

main().catch((error) => {
  console.error('冒烟脚本异常:', error);
  process.exit(1);
});
