// LLM 闭环回放测试（faux provider）— 不触网、不连 DB、不起 Python，纯代码层验证：
//   createPlannerModel(faux) → createPlannerAgent → agent.prompt() → 事件流落库（内存 sink）
//   + Run 硬超时（agent.abort() 降级人工）
//   + validation 硬闸门（确定性校验拦截非法方案）
//
// 注意：pi 两包是 ESM-only，经 runtime-loader 的 new Function 动态 import 加载；
// Jest 需以 --experimental-vm-modules 启动（package.json test 脚本已带）。

import type { PiAi } from '@/agents/core/runtime-loader';
import { loadPiRuntime } from '@/agents/core/runtime-loader';
import type { WorkerDefinition } from '@/agents/core/worker-runtime.interface';
import type { WorkerResult } from '@/contracts/worker-result';
import type { WorkerTask } from '@/contracts/worker-task';
import { WorkerRegistry } from '@/registry/worker-registry';
import { WorkerRouter } from '@/orchestration/worker-router';
import { PlannerOrchestrator } from '@/orchestration/planner-orchestrator';
import { RunEventBus } from '@/orchestration/run-event-bus';
import type { DispatchRepository } from '@/services/db/dispatch.repo';

// ESM 冷加载约 8s，放宽单测超时。
jest.setTimeout(30_000);

let pi: PiAi;

beforeAll(async () => {
  ({ ai: pi } = await loadPiRuntime());
});

// ── 内存 repo：结构化满足 DispatchRepository 用到的子集（落库断言对象）──
interface MemoryRun {
  id: string;
  planId: string;
  status: string;
  payload?: unknown;
  finishedAt?: Date;
}

class MemoryRepo {
  readonly runs: MemoryRun[] = [];
  readonly workerExecutions: Array<Record<string, unknown>> = [];
  readonly events: Array<Record<string, unknown>> = [];

  async createPlan(input: any) {
    return input;
  }
  async createRun(input: any) {
    this.runs.push(input);
    return input;
  }
  async updateRunStatus(id: string, status: string, finished = false) {
    const run = this.runs.find((r) => r.id === id);
    if (run) {
      run.status = status;
      if (finished) run.finishedAt = new Date();
    }
  }
  async finalizeRun(id: string, input: { status: string; payload?: unknown }) {
    const run = this.runs.find((r) => r.id === id);
    if (run) {
      run.status = input.status;
      if (input.payload !== undefined) run.payload = input.payload;
      run.finishedAt = new Date();
    }
  }
  async recordWorkerExecution(input: any) {
    this.workerExecutions.push(input);
    return input;
  }
  async listWorkerExecutions(runId: string) {
    return this.workerExecutions.filter((e) => e.runId === runId);
  }
  async appendEvent(input: any) {
    this.events.push(input);
  }
}

// ── faux Worker：脚本化返回 WorkerResult，不调 Python ──
function fauxAllocationDefinition(
  makeResult: (task: WorkerTask) => WorkerResult,
): WorkerDefinition {
  return {
    capability: 'allocation.assign',
    workerType: 'allocation-worker',
    description: 'faux allocation worker（测试替身）',
    runtimeFactory: () => ({
      run: async (task: WorkerTask) => makeResult(task),
    }),
  };
}

function successResult(task: WorkerTask, allocations: WorkerResult['result']): WorkerResult {
  return {
    taskId: task.taskId,
    correlationId: task.correlationId,
    planId: task.planId,
    runId: task.runId,
    workerType: 'allocation-worker',
    capability: 'allocation.assign',
    attempt: task.attempt,
    status: 'success',
    result: allocations,
  };
}

/** 装配一次闭环：faux provider + 内存 repo + faux Worker + Orchestrator（模型工厂注入 faux）。 */
function setupLoop(options: {
  responses: ReturnType<PiAi['fauxAssistantMessage']>[];
  makeResult: (task: WorkerTask) => WorkerResult;
  fauxOptions?: Parameters<PiAi['fauxProvider']>[0];
}) {
  const faux = pi.fauxProvider(options.fauxOptions);
  const models = pi.createModels();
  models.setProvider(faux.provider);
  faux.setResponses(options.responses);

  const registry = new WorkerRegistry();
  registry.register(fauxAllocationDefinition(options.makeResult));
  const router = new WorkerRouter(registry);
  const repo = new MemoryRepo();
  const bus = new RunEventBus();
  const orchestrator = new PlannerOrchestrator(repo as unknown as DispatchRepository, router, bus);
  orchestrator.createModelHandle = async () => ({ models, model: faux.getModel() });
  return { orchestrator, repo, bus, faux };
}

const FULL_PLAN = {
  allocations: [
    { uav_id: 'uav-1', task_id: 'task-1', estimated_cost: 10 },
    { uav_id: 'uav-2', task_id: 'task-2', estimated_cost: 12 },
  ],
  unassigned_tasks: [],
  algorithm_used: 'hungarian',
};

describe('LLM 闭环（faux 回放）：createPlannerModel → createPlannerAgent → prompt → 事件流落库', () => {
  it('完整闭环：Planner 调 assign_tasks → Worker 返回方案 → validation 通过 → COMPLETED，事件流全部落库', async () => {
    const { orchestrator, repo } = setupLoop({
      responses: [
        // 第 1 轮：模型发起 assign_tasks 工具调用
        pi.fauxAssistantMessage([
          pi.fauxToolCall('assign_tasks', { uavIds: ['uav-1', 'uav-2'], taskIds: ['task-1', 'task-2'] }),
        ]),
        // 第 2 轮：模型基于工具结果给出结论
        pi.fauxAssistantMessage('方案：task-1→uav-1，task-2→uav-2'),
      ],
      makeResult: (task) => successResult(task, FULL_PLAN),
    });

    const outcome = await orchestrator.execute({ objective: 'XX 区域火灾侦察' });

    // 终态
    expect(outcome.status).toBe('completed');
    expect(outcome.message).toContain('2 项分配');
    expect(repo.runs).toHaveLength(1);
    expect(repo.runs[0].status).toBe('completed');
    expect(repo.runs[0].finishedAt).toBeInstanceOf(Date);

    // 终态 payload：方案 + 转录快照
    const payload = repo.runs[0].payload as { plan: typeof FULL_PLAN; transcript: unknown[] };
    expect(payload.plan.allocations).toHaveLength(2);
    expect(Array.isArray(payload.transcript)).toBe(true);
    expect(payload.transcript.length).toBeGreaterThan(0);

    // 事件流落库：turn_start / turn_end（两轮）
    const turnEvents = repo.events.filter((e) => e.type === 'turn_start' || e.type === 'turn_end');
    expect(turnEvents).toHaveLength(4); // 2 轮 × (start + end)
    const turnEnd = repo.events.find((e) => e.type === 'turn_end');
    expect((turnEnd?.payload as { stopReason: string }).stopReason).toBe('stop');

    // worker_executions 落库（afterToolCall 钩子）
    expect(repo.workerExecutions).toHaveLength(1);
    expect(repo.workerExecutions[0]).toMatchObject({
      capability: 'allocation.assign',
      workerType: 'allocation-worker',
      status: 'success',
    });
    expect(typeof repo.workerExecutions[0].durationMs).toBe('number');
  });

  it('状态机流转：planning → executing（agent_start）→ validating → completed', async () => {
    const seen: string[] = [];
    const { orchestrator, repo } = setupLoop({
      responses: [
        pi.fauxAssistantMessage([pi.fauxToolCall('assign_tasks', { uavIds: ['uav-1'], taskIds: ['task-1'] })]),
        pi.fauxAssistantMessage('完成'),
      ],
      makeResult: (task) =>
        successResult(task, {
          allocations: [{ uav_id: 'uav-1', task_id: 'task-1', estimated_cost: 5 }],
          unassigned_tasks: [],
          algorithm_used: 'hungarian',
        }),
    });

    // 包一层 repo 观察状态流转
    const rawUpdate = repo.updateRunStatus.bind(repo);
    repo.updateRunStatus = async (id, status, finished) => {
      seen.push(status);
      return rawUpdate(id, status, finished);
    };
    const rawFinalize = repo.finalizeRun.bind(repo);
    repo.finalizeRun = async (id, input) => {
      seen.push(input.status);
      return rawFinalize(id, input);
    };

    await orchestrator.execute({ objective: '状态机测试' });
    expect(seen).toEqual(['executing', 'validating', 'completed']);
  });

  it('validation 硬闸门：任务重复分配 → FAILED，violations 落库，不置 COMPLETED', async () => {
    const { orchestrator, repo } = setupLoop({
      responses: [
        pi.fauxAssistantMessage([
          pi.fauxToolCall('assign_tasks', { uavIds: ['uav-1', 'uav-2'], taskIds: ['task-1'] }),
        ]),
        pi.fauxAssistantMessage('方案（有冲突）'),
      ],
      makeResult: (task) =>
        successResult(task, {
          // task-1 被分配了两次 —— 确定性校验必须拦截
          allocations: [
            { uav_id: 'uav-1', task_id: 'task-1', estimated_cost: 10 },
            { uav_id: 'uav-2', task_id: 'task-1', estimated_cost: 12 },
          ],
          unassigned_tasks: [],
          algorithm_used: 'hungarian',
        }),
    });

    const outcome = await orchestrator.execute({ objective: '冲突方案测试' });

    expect(outcome.status).toBe('failed');
    expect(outcome.message).toContain('validation 硬闸门拦截');
    expect(repo.runs[0].status).toBe('failed');
    const payload = repo.runs[0].payload as { reason: string; violations: string[] };
    expect(payload.reason).toBe('validation_rejected');
    expect(payload.violations).toContain('task assigned more than once: task-1');
  });

  it('validation 硬闸门：请求任务在方案中丢失 → FAILED', async () => {
    const { orchestrator, repo } = setupLoop({
      responses: [
        pi.fauxAssistantMessage([
          pi.fauxToolCall('assign_tasks', { uavIds: ['uav-1'], taskIds: ['task-1', 'task-2'] }),
        ]),
        pi.fauxAssistantMessage('方案（漏了 task-2）'),
      ],
      makeResult: (task) =>
        successResult(task, {
          allocations: [{ uav_id: 'uav-1', task_id: 'task-1', estimated_cost: 10 }],
          unassigned_tasks: [], // task-2 既没分配也没进未分配 —— 静默丢失
          algorithm_used: 'hungarian',
        }),
    });

    const outcome = await orchestrator.execute({ objective: '丢任务测试' });
    expect(outcome.status).toBe('failed');
    const payload = repo.runs[0].payload as { violations: string[] };
    expect(payload.violations).toContain('requested task missing from plan: task-2');
  });

  it('Planner 未调工具（无方案）→ FAILED（no_plan）', async () => {
    const { orchestrator, repo } = setupLoop({
      responses: [pi.fauxAssistantMessage('我直接回答，不调用任何工具')],
      makeResult: (task) => successResult(task, FULL_PLAN),
    });

    const outcome = await orchestrator.execute({ objective: '无方案测试' });
    expect(outcome.status).toBe('failed');
    expect(outcome.message).toContain('no_plan');
    expect((repo.runs[0].payload as { reason: string }).reason).toBe('no_plan');
  });
});

describe('Run 硬超时：ctx.timeoutMs → agent.abort() → 降级人工接管', () => {
  it('慢速流被 abort → FAILED（run_timeout），不挂起', async () => {
    const { orchestrator, repo } = setupLoop({
      // tokensPerSecond=20：400 字符 ≈ 100 tokens，完整流完约 5s，远超 300ms 预算
      responses: [pi.fauxAssistantMessage('x'.repeat(400))],
      makeResult: (task) => successResult(task, FULL_PLAN),
      fauxOptions: { tokensPerSecond: 20 },
    });

    const started = Date.now();
    const outcome = await orchestrator.execute({ objective: '超时测试', timeoutMs: 300 });
    const elapsed = Date.now() - started;

    expect(outcome.status).toBe('failed');
    expect(outcome.message).toContain('run_timeout');
    expect(outcome.message).toContain('降级人工接管');
    expect(repo.runs[0].status).toBe('failed');
    expect((repo.runs[0].payload as { reason: string }).reason).toBe('run_timeout');
    // 超时后应迅速收敛（abort 中断流式响应），不会跑满 5s
    expect(elapsed).toBeLessThan(3_000);
  }, 15_000);

  it('未超时的正常流程不受超时机制影响（预算充足 → COMPLETED）', async () => {
    const { orchestrator } = setupLoop({
      responses: [
        pi.fauxAssistantMessage([pi.fauxToolCall('assign_tasks', { uavIds: ['uav-1'], taskIds: ['task-1'] })]),
        pi.fauxAssistantMessage('完成'),
      ],
      makeResult: (task) =>
        successResult(task, {
          allocations: [{ uav_id: 'uav-1', task_id: 'task-1', estimated_cost: 5 }],
          unassigned_tasks: [],
          algorithm_used: 'hungarian',
        }),
    });

    const outcome = await orchestrator.execute({ objective: '正常流程', timeoutMs: 10_000 });
    expect(outcome.status).toBe('completed');
  });
});

describe('SSE 推流（start 非阻塞 + RunEventBus 事件流）', () => {
  it('start() 立即返回 runId，事件经总线按序推送，run_end 携带终态', async () => {
    const { orchestrator, repo, bus } = setupLoop({
      responses: [
        pi.fauxAssistantMessage([pi.fauxToolCall('assign_tasks', { uavIds: ['uav-1', 'uav-2'], taskIds: ['task-1', 'task-2'] })]),
        pi.fauxAssistantMessage('完成'),
      ],
      makeResult: (task) => successResult(task, FULL_PLAN),
    });

    // 订阅放在 start() 之后：验证「晚到订阅」也能经回放+实时拿到全程
    const receipt = await orchestrator.start({ objective: '推流测试' });
    expect(receipt.runId).toBeTruthy();
    expect(receipt.planId).toBeTruthy();

    const events: Array<{ type: string; data?: unknown }> = [];
    await new Promise<void>((resolve) => {
      bus.stream(receipt.runId).subscribe({
        next: (event) => events.push({ type: event.type, data: event.data }),
        complete: () => resolve(),
      });
    });

    const types = events.map((e) => e.type);
    expect(types[0]).toBe('run_start');
    expect(types).toContain('agent_start');
    expect(types).toContain('tool_execution_start');
    expect(types).toContain('tool_execution_end');
    expect(types[types.length - 1]).toBe('run_end');
    // token 级噪声事件不透传
    expect(types).not.toContain('message_update');
    expect(types).not.toContain('tool_execution_update');
    // run_end 携带终态 outcome，前端据此收尾
    expect(events[events.length - 1].data).toMatchObject({ status: 'completed' });
    // 落库侧同样到达终态（推流与持久化双通道一致）
    expect(repo.runs[0].status).toBe('completed');
  }, 15_000);

  it('start() 不等闭环结束即返回（非阻塞语义）', async () => {
    const { orchestrator, bus } = setupLoop({
      // 慢速流：若 start 阻塞则会等满整个流式过程
      responses: [pi.fauxAssistantMessage('x'.repeat(80))],
      makeResult: (task) => successResult(task, FULL_PLAN),
      fauxOptions: { tokensPerSecond: 20 },
    });

    const started = Date.now();
    const receipt = await orchestrator.start({ objective: '非阻塞测试', timeoutMs: 5_000 });
    const elapsed = Date.now() - started;

    expect(receipt.runId).toBeTruthy();
    // 创建 Plan+Run 两条 insert 的耗时，远小于慢速流的秒级耗时
    expect(elapsed).toBeLessThan(1_000);

    // 等后台闭环收敛（run_end）再结束用例，避免残留 timer 拖住 Jest
    await new Promise<void>((resolve) => {
      bus.stream(receipt.runId).subscribe({ complete: () => resolve() });
    });
  }, 15_000);
});
