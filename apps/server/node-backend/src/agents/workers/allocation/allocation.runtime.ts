// Allocation Worker — capability `allocation.assign` 的确定型执行器。
// 职责：领域输入整形 → 选算法（确定性规则）→ 调 Python 算法服务 → 领域解读 → 统一 WorkerResult。
// 注意：Worker 是"领域能力"不是"算法"；Hungarian/Auction 在 Python 端，这里只做编排与解读。

import type { WorkerRuntime } from '@/agents/core/worker-runtime.interface';
import type { WorkerTask } from '@/contracts/worker-task';
import type { WorkerResult } from '@/contracts/worker-result';
import { selectAllocationAlgorithm } from '@/agents/workers/allocation/algorithm-selector';
import type { AlgorithmClient } from '@/services/python/python-client';

/** 领域强类型 input（模型参数经 TypeBox 校验后包成 WorkerTask.input）。 */
export interface AllocationInput {
  uavIds: string[];
  taskIds: string[];
  /** 可选：显式指定算法（透传）。 */
  algorithm?: string;
}

export class AllocationWorkerRuntime implements WorkerRuntime {
  constructor(private readonly python: AlgorithmClient) {}

  async run(task: WorkerTask, signal?: AbortSignal): Promise<WorkerResult> {
    const input = task.input as AllocationInput;
    // TODO Phase 2：input 的 zod 兜底校验 + uav/task 载荷从 domain 服务补全
    const algorithm = selectAllocationAlgorithm({
      taskCount: input.taskIds?.length,
      uavCount: input.uavIds?.length,
      requested: input.algorithm,
    });

    try {
      const response = await this.python.allocateTasks(
        { uavIds: input.uavIds ?? [], taskIds: input.taskIds ?? [], algorithm },
        { signal },
      );
      // TODO Phase 2：领域解读（分配方案/未分配/冲突 → result + feedback）
      return {
        taskId: task.taskId,
        correlationId: task.correlationId,
        planId: task.planId,
        runId: task.runId,
        workerType: 'allocation-worker',
        capability: 'allocation.assign',
        attempt: task.attempt,
        status: 'success',
        result: response,
      };
    } catch (error) {
      // 网关错误（AlgorithmError）已带 code/retryable；其余错误按不可重试处理。
      const e = error as { code?: string; message?: string; retryable?: boolean };
      return {
        taskId: task.taskId,
        correlationId: task.correlationId,
        planId: task.planId,
        runId: task.runId,
        workerType: 'allocation-worker',
        capability: 'allocation.assign',
        attempt: task.attempt,
        status: 'failed',
        error: {
          code: e.code ?? 'ALLOCATION_FAILED',
          message: e.message ?? String(error),
          retryable: e.retryable ?? false,
        },
      };
    }
  }
}
