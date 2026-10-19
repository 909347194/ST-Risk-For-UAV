// assign_tasks 工具测试 — 锁定 ① 修复：WorkerTask 的 planId/runId 从 runContext 绑定（不再空串）。
// 用假 ai 命名空间（Type/uuidv7 仅构造期使用），不加载 pi 运行时。

import { createAssignTasksTool } from '@/agents/planner/tools/assign-tasks.tool';
import type { PiAi } from '@/agents/core/runtime-loader';
import type { DispatchFn } from '@/orchestration/worker-router';
import type { WorkerTask } from '@/contracts/worker-task';
import type { WorkerResult } from '@/contracts/worker-result';

const fakeAi = {
  Type: {
    Object: (props: unknown) => props,
    Array: (item: unknown) => item,
    String: () => ({}),
    Optional: (item: unknown) => item,
  },
  uuidv7: () => 'uuidv7-1',
} as unknown as Pick<PiAi, 'Type' | 'uuidv7'>;

function okResult(task: WorkerTask): WorkerResult {
  return {
    taskId: task.taskId,
    correlationId: task.correlationId,
    planId: task.planId,
    runId: task.runId,
    workerType: task.workerType,
    capability: task.capability,
    attempt: task.attempt,
    status: 'success',
    result: { assignments: [] },
  };
}

describe('createAssignTasksTool — WorkerTask 上下文绑定（修复①）', () => {
  it('planId/runId 从 runContext 绑定，correlationId=toolCallId，taskId=uuidv7', async () => {
    const seen: WorkerTask[] = [];
    const dispatch: DispatchFn = async (_capability, task) => {
      seen.push(task);
      return okResult(task);
    };
    const tool = createAssignTasksTool(fakeAi, dispatch, { planId: 'plan-42', runId: 'run-42' });

    await tool.execute('call-1', { uavIds: ['u1'], taskIds: ['t1'] });

    expect(seen[0]).toMatchObject({
      taskId: 'uuidv7-1',
      correlationId: 'call-1',
      planId: 'plan-42',
      runId: 'run-42',
      capability: 'allocation.assign',
      attempt: 0,
    });
  });

  it('WorkerResult 回填 correlationId 到工具结果 details', async () => {
    const dispatch: DispatchFn = async (_c, task) => ({ ...okResult(task), correlationId: undefined });
    const tool = createAssignTasksTool(fakeAi, dispatch, { planId: 'p', runId: 'r' });

    const out = await tool.execute('call-9', { uavIds: [], taskIds: [] });

    expect((out.details as WorkerResult).correlationId).toBe('call-9');
    expect(out.terminate).toBeUndefined();
  });

  it('派发类工具：executionMode=sequential 且 replay=never', () => {
    const tool = createAssignTasksTool(fakeAi, async () => okResult({} as WorkerTask), {
      planId: 'p',
      runId: 'r',
    });
    expect(tool.executionMode).toBe('sequential');
    expect(tool.replay).toBe('never');
    expect(tool.label).toBeTruthy();
  });
});
