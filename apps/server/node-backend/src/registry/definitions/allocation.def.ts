// Worker 定义静态注册 — allocation.assign 能力。
// V1 静态注册（启动装配），不做远程注册中心；每加一个能力 = 新增一个 definitions 文件 + 一行注册。

import type { WorkerDefinition } from '@/agents/core/worker-runtime.interface';
import { AllocationWorkerRuntime } from '@/agents/workers/allocation/allocation.runtime';
import type { AlgorithmClient } from '@/services/python/python-client';

export function allocationWorkerDefinition(python: AlgorithmClient): WorkerDefinition {
  return {
    capability: 'allocation.assign',
    workerType: 'allocation-worker',
    description: '将任务分配给可用无人机（Hungarian/Auction，算法在 Python 端），返回分配方案',
    runtimeFactory: () => new AllocationWorkerRuntime(python),
  };
}
