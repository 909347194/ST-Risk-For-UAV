// 锁定 pi 工具结果约定（见 docs/architecture/agent-architecture-node-landing.md 第 4.2 节）：
//  - failed    → throw（运行时以 isError:true 交还模型自纠）
//  - need_input → terminate: true（提示停轮）
//  - success / partial → 正常 content + details
//
// 本文件只触碰纯函数，不加载 pi 运行时（planner-tool.ts 全部 import type），无 ESM 依赖。

import { toAgentToolResult, workerResultToToolResult } from '@/agents/core/planner-tool';
import type { WorkerResult } from '@/contracts/worker-result';

const base: Omit<WorkerResult, 'status'> = {
  taskId: 'task-1',
  planId: 'plan-1',
  runId: 'run-1',
  workerType: 'allocation-worker',
  result: { assignments: [{ uavId: 'uav-1', taskId: 't-1' }] },
};

describe('workerResultToToolResult — pi 工具结果约定', () => {
  it('success → 返回 content + details，不设 terminate', () => {
    const out = workerResultToToolResult({ ...base, status: 'success' });
    expect(out.content).toEqual([
      { type: 'text', text: JSON.stringify(base.result) },
    ]);
    expect(out.details.status).toBe('success');
    expect(out.terminate).toBeUndefined();
  });

  it('partial → 正常返回（部分成功不是错误）', () => {
    const out = workerResultToToolResult({ ...base, status: 'partial' });
    expect(out.details.status).toBe('partial');
    expect(out.terminate).toBeUndefined();
  });

  it('failed → throw（不得把错误包成成功 content）', () => {
    const failed: WorkerResult = {
      ...base,
      status: 'failed',
      result: undefined,
      error: { code: 'E_ALLOC', message: 'no feasible allocation', retryable: true },
    };
    expect(() => workerResultToToolResult(failed)).toThrow(
      /\[allocation-worker\] E_ALLOC: no feasible allocation/,
    );
  });

  it('failed 且无 error 详情 → 仍 throw，带默认文案', () => {
    const failed: WorkerResult = { ...base, status: 'failed', result: undefined };
    expect(() => workerResultToToolResult(failed)).toThrow(
      /\[allocation-worker\] WORKER_FAILED: worker execution failed/,
    );
  });

  it('need_input → terminate: true（提示停轮等待人工补充信息）', () => {
    const out = workerResultToToolResult({ ...base, status: 'need_input', result: undefined });
    expect(out.terminate).toBe(true);
  });
});

describe('toAgentToolResult — 成功路径包装', () => {
  it('把结构化结果包成 text content + details', () => {
    const out = toAgentToolResult({ hello: 'world' });
    expect(out.content).toEqual([{ type: 'text', text: '{"hello":"world"}' }]);
    expect(out.details).toEqual({ hello: 'world' });
  });
});
