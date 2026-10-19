// Allocation Worker — capability `allocation.assign` 的确定型执行器。
// 职责：领域输入整形 → 选算法（确定性规则）→ 调 Python 算法服务 → 领域解读 → 统一 WorkerResult。
// 注意：Worker 是"领域能力"不是"算法"；Hungarian/Auction 在 Python 端，这里只做编排与解读。
// 接口契约：docs/architecture/python-api-contract.md（Python AllocateRequest 要完整 UAV/Task 对象）。

import type { WorkerRuntime } from '@/agents/core/worker-runtime.interface';
import type { WorkerTask } from '@/contracts/worker-task';
import type { WorkerResult } from '@/contracts/worker-result';
import { selectAllocationAlgorithm } from '@/agents/workers/allocation/algorithm-selector';
import type {
  AlgorithmClient,
  TaskPayload,
  UavPayload,
} from '@/services/python/python-client';

/** 领域强类型 input（模型参数经 TypeBox 校验后包成 WorkerTask.input）。 */
export interface AllocationInput {
  uavIds: string[];
  taskIds: string[];
  /** 可选：显式指定算法（透传）。 */
  algorithm?: string;
}

/**
 * 载荷补全依赖：按 ID 加载完整 UAV/Task 对象（Python 端要完整对象，不是 ID 列表）。
 * Phase 2 接 Drizzle/domain 服务实现；未注入时 Worker 返回明确的配置错误，不发无效请求。
 */
export interface AllocationPayloadLoader {
  loadUavs(ids: string[], signal?: AbortSignal): Promise<UavPayload[]>;
  loadTasks(ids: string[], signal?: AbortSignal): Promise<TaskPayload[]>;
}

export class AllocationWorkerRuntime implements WorkerRuntime {
  constructor(
    private readonly python: AlgorithmClient,
    private readonly loader?: AllocationPayloadLoader,
  ) {}

  async run(task: WorkerTask, signal?: AbortSignal): Promise<WorkerResult> {
    const input = task.input as AllocationInput;
    const base = {
      taskId: task.taskId,
      correlationId: task.correlationId,
      planId: task.planId,
      runId: task.runId,
      workerType: 'allocation-worker',
      capability: 'allocation.assign',
      attempt: task.attempt,
    };

    if (!this.loader) {
      // 配置错误要早暴露：Python 端要求完整对象，禁止发 ID 空壳凑数。
      return {
        ...base,
        status: 'failed',
        error: {
          code: 'PAYLOAD_LOADER_MISSING',
          message: 'AllocationPayloadLoader not configured; cannot load full UAV/Task payloads',
          retryable: false,
        },
      };
    }

    try {
      const [uavs, tasks] = await Promise.all([
        this.loader.loadUavs(input.uavIds ?? [], signal),
        this.loader.loadTasks(input.taskIds ?? [], signal),
      ]);
      const algorithm = selectAllocationAlgorithm({
        taskCount: tasks.length,
        uavCount: uavs.length,
        requested: input.algorithm,
      });

      const response = await this.python.allocateTasks(
        { uavs, tasks, algorithm },
        { signal, correlationId: task.correlationId },
      );

      // TODO Phase 2：领域解读（分配方案/未分配/冲突 → result + feedback）
      return {
        ...base,
        status: 'success',
        result: response,
      };
    } catch (error) {
      // 网关错误（AlgorithmError）已带 code/retryable；其余错误按不可重试处理。
      const e = error as { code?: string; message?: string; retryable?: boolean };
      return {
        ...base,
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
