// WorkerRouter / WorkerRegistry 单测 — capability 解耦与边界校验。

import type { WorkerTask } from '@/contracts/worker-task';
import type { WorkerResult } from '@/contracts/worker-result';
import type { WorkerDefinition, WorkerRuntime } from '@/agents/core/worker-runtime.interface';
import { WorkerRegistry } from '@/registry/worker-registry';
import { WorkerRouter } from '@/orchestration/worker-router';

function task(patch: Partial<WorkerTask> = {}): WorkerTask {
  return {
    taskId: 'task-1',
    correlationId: 'call-1',
    planId: 'plan-1',
    runId: 'run-1',
    workerType: 'allocation-worker',
    capability: 'allocation.assign',
    objective: 'assign',
    input: {},
    attempt: 0,
    schemaVersion: '1.0.0',
    ...patch,
  };
}

function result(patch: Partial<WorkerResult> = {}): WorkerResult {
  return {
    taskId: 'task-1',
    planId: 'plan-1',
    runId: 'run-1',
    workerType: 'allocation-worker',
    status: 'success',
    ...patch,
  };
}

function definition(capability: string, runtime: WorkerRuntime): WorkerDefinition {
  return { capability, workerType: 'test-worker', description: 'test', runtimeFactory: () => runtime };
}

describe('WorkerRegistry', () => {
  it('register / resolve / list', () => {
    const registry = new WorkerRegistry();
    const def = definition('allocation.assign', { run: async () => result() });
    registry.register(def);
    expect(registry.resolve('allocation.assign')).toBe(def);
    expect(registry.list()).toHaveLength(1);
  });

  it('重复注册同 capability 直接抛错', () => {
    const registry = new WorkerRegistry();
    const def = definition('x.y', { run: async () => result() });
    registry.register(def);
    expect(() => registry.register(def)).toThrow(/already registered/);
  });
});

describe('WorkerRouter — capability 解耦 + 边界校验', () => {
  it('按 capability 分发给注册的 runtime', async () => {
    const registry = new WorkerRegistry();
    const seen: WorkerTask[] = [];
    registry.register(
      definition('allocation.assign', {
        run: async (t) => {
          seen.push(t);
          return result();
        },
      }),
    );
    const router = new WorkerRouter(registry);
    const out = await router.dispatch('allocation.assign', task());
    expect(out.status).toBe('success');
    expect(seen[0].correlationId).toBe('call-1');
  });

  it('未注册 capability → 抛错（工具侧 throw 交还模型）', async () => {
    const router = new WorkerRouter(new WorkerRegistry());
    await expect(router.dispatch('nope.cap', task())).rejects.toThrow(/no worker registered/);
  });

  it('runtime 返回违反契约 → zod 边界校验炸掉，不放脏数据过界', async () => {
    const registry = new WorkerRegistry();
    registry.register(
      definition('bad.result', {
        run: async () => ({ taskId: 'x' }) as unknown as WorkerResult,
      }),
    );
    const router = new WorkerRouter(registry);
    await expect(router.dispatch('bad.result', task())).rejects.toThrow();
  });
});
