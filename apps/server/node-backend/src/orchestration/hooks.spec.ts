// orchestration 三钩子单测：执行策略（beforeToolCall）/ Feedback（afterToolCall）/ Replanner（finishTurn）。
// 遵循 pi：这些是 Agent 钩子工厂，不是自研调度框架——测试直接按 pi 的钩子签名驱动。
// 纯 TS，不加载 pi 运行时（全部 import type），无 ESM 依赖。

import type { AfterToolCallContext, BeforeToolCallContext } from '@earendil-works/pi-agent-core';
import type { WorkerResult } from '@/contracts/worker-result';
import { createBeforeToolCallHook, type ToolCallTracker } from '@/orchestration/execution-policy';
import {
  createAfterToolCallHook,
  ToolExecutionTracker,
  type DispatchRecordSink,
} from '@/orchestration/feedback-handler';
import { createFinishTurnHook } from '@/orchestration/replanner';

const toolCall = { id: 'call-1', name: 'assign_tasks', arguments: {} } as any;

function beforeCtx(): BeforeToolCallContext {
  return {
    assistantMessage: {} as any,
    toolCall,
    args: {},
    context: { messages: [], tools: [] },
  };
}

function afterCtx(details: WorkerResult | undefined, isError = false): AfterToolCallContext {
  return {
    assistantMessage: {} as any,
    toolCall,
    args: {},
    result: {
      content: [{ type: 'text', text: 'ok' }],
      details,
    } as any,
    isError,
    context: { messages: [], tools: [] },
  };
}

function workerResult(patch: Partial<WorkerResult> = {}): WorkerResult {
  return {
    taskId: 'task-1',
    correlationId: 'call-1',
    planId: 'plan-1',
    runId: 'run-1',
    workerType: 'allocation-worker',
    capability: 'allocation.assign',
    attempt: 1,
    status: 'success',
    result: { ok: 1 },
    ...patch,
  };
}

describe('createBeforeToolCallHook — 执行策略（pi beforeToolCall）', () => {
  it('默认放行（返回 undefined），并登记开始时间', async () => {
    const started: string[] = [];
    const tracker: ToolCallTracker = { start: (id) => started.push(id) };
    const hook = createBeforeToolCallHook({ tracker });
    expect(await hook(beforeCtx())).toBeUndefined();
    expect(started).toEqual(['call-1']);
  });

  it('Run 已取消 → block + terminate', async () => {
    const hook = createBeforeToolCallHook({ isRunCancelled: () => true });
    expect(await hook(beforeCtx())).toEqual({
      block: true,
      reason: 'run cancelled',
      terminate: true,
    });
  });

  it('工具不在白名单 → block（不 terminate，模型可换路）', async () => {
    const hook = createBeforeToolCallHook({ allowTool: (name) => name !== 'assign_tasks' });
    const out = await hook(beforeCtx());
    expect(out?.block).toBe(true);
    expect(out?.terminate).toBeUndefined();
  });

  it('超过 maxCallsPerTool → block + terminate（防无限重试）', async () => {
    const hook = createBeforeToolCallHook({ maxCallsPerTool: 2 });
    expect((await hook(beforeCtx()))?.block).toBeUndefined();
    expect((await hook(beforeCtx()))?.block).toBeUndefined();
    const out = await hook(beforeCtx());
    expect(out).toMatchObject({ block: true, terminate: true });
    expect(out?.reason).toContain('retry limit reached');
  });
});

describe('createAfterToolCallHook — 执行追溯 + 反馈事件（pi afterToolCall）', () => {
  function fakeSink() {
    const executions: any[] = [];
    const events: any[] = [];
    const sink: DispatchRecordSink = {
      recordWorkerExecution: async (input) => void executions.push(input),
      appendEvent: async (input) => void events.push(input),
    };
    return { sink, executions, events };
  }

  it('成功 → 落 worker_executions（含 durationMs/correlation 信息），无反馈不发事件', async () => {
    const { sink, executions, events } = fakeSink();
    const tracker = new ToolExecutionTracker();
    tracker.start('call-1');
    const hook = createAfterToolCallHook({
      runId: 'run-1',
      sink,
      tracker,
      genId: () => 'id-1',
    });
    expect(await hook(afterCtx(workerResult()))).toBeUndefined();
    expect(executions).toHaveLength(1);
    expect(executions[0]).toMatchObject({
      id: 'id-1',
      runId: 'run-1',
      taskId: 'task-1',
      capability: 'allocation.assign',
      workerType: 'allocation-worker',
      attempt: 1,
      status: 'success',
    });
    expect(typeof executions[0].durationMs).toBe('number');
    expect(events).toHaveLength(0);
  });

  it('isError → 落库 status=failed', async () => {
    const { sink, executions } = fakeSink();
    const hook = createAfterToolCallHook({ runId: 'run-1', sink, genId: () => 'id-2' });
    await hook(afterCtx(workerResult({ status: 'failed' }), true));
    expect(executions[0]).toMatchObject({ status: 'failed' });
  });

  it('feedback.type !== none → 追加 dispatch_event', async () => {
    const { sink, events } = fakeSink();
    const hook = createAfterToolCallHook({ runId: 'run-1', sink, genId: () => 'id-3' });
    await hook(
      afterCtx(
        workerResult({
          status: 'partial',
          feedback: { type: 'replan', reason: 'conflict', affectedTaskIds: ['t-2'] },
        }),
      ),
    );
    expect(events).toHaveLength(1);
    expect(events[0]).toMatchObject({
      id: 'id-3',
      runId: 'run-1',
      type: 'replan',
      reason: 'conflict',
      payload: { correlationId: 'call-1', affectedTaskIds: ['t-2'] },
    });
  });

  it('feedback.type=none 不发事件；落库失败走 onError 且不抛出', async () => {
    const errors: unknown[] = [];
    const sink: DispatchRecordSink = {
      recordWorkerExecution: async () => {
        throw new Error('db down');
      },
      appendEvent: async () => undefined,
    };
    const hook = createAfterToolCallHook({
      runId: 'run-1',
      sink,
      genId: () => 'id-4',
      onError: (e) => errors.push(e),
    });
    await expect(
      hook(afterCtx(workerResult({ feedback: { type: 'none', reason: '' } }))),
    ).resolves.toBeUndefined();
    expect(errors).toHaveLength(1);
  });
});

describe('createFinishTurnHook — Replanner 决策（pi finishTurn）', () => {
  function turn(stopReason: string) {
    return {
      message: { stopReason },
      toolResults: [],
      context: { messages: [], tools: [] },
      newMessages: [],
    } as any;
  }

  it('error/aborted 硬退出守卫 → undefined（不干预）', async () => {
    const hook = createFinishTurnHook({ shouldContinue: () => true });
    expect(await hook(turn('error'))).toBeUndefined();
    expect(await hook(turn('aborted'))).toBeUndefined();
  });

  it('maxTurns 收敛 → { action: "end" }', async () => {
    const hook = createFinishTurnHook({ maxTurns: 2 });
    expect(await hook(turn('stop'))).toBeUndefined(); // 保持正常调度
    expect(await hook(turn('stop'))).toEqual({ action: 'end' });
  });

  it('shouldContinue=true → continue；false → end', async () => {
    const yes = createFinishTurnHook({ shouldContinue: () => true });
    expect(await yes(turn('stop'))).toEqual({ action: 'continue' });
    const no = createFinishTurnHook({ shouldContinue: () => false });
    expect(await no(turn('stop'))).toEqual({ action: 'end' });
  });

  it('未配置判定 → undefined（保留 pi 正常调度）', async () => {
    const hook = createFinishTurnHook();
    expect(await hook(turn('stop'))).toBeUndefined();
  });
});
