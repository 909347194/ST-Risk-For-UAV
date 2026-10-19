// Worker Router — 按 capability 把 WorkerTask 分发给注册的 WorkerRuntime。
// 这是"Planner 不直接持有 Worker 具体类"的落点：工具只调 dispatch，不 new Worker。
// 回收结果过 zod 边界校验（parseWorkerResult）——脏数据炸在边界，不传给 Planner。

import type { WorkerTask } from '@/contracts/worker-task';
import type { WorkerResult } from '@/contracts/worker-result';
import { parseWorkerResult } from '@/contracts/runtime-schema';
import type { WorkerRegistry } from '@/registry/worker-registry';

/** Planner 工具委派 Worker 的函数签名（由 Router.dispatch 绑定后注入工具）。 */
export type DispatchFn = (capability: string, task: WorkerTask, signal?: AbortSignal) => Promise<WorkerResult>;

export class WorkerRouter {
  constructor(private readonly registry: WorkerRegistry) {}

  /** 已注册能力视图（供 system-prompt 动态生成能力清单等）。 */
  listCapabilities(): { capability: string; description: string }[] {
    return this.registry.list().map((d) => ({ capability: d.capability, description: d.description }));
  }

  dispatch: DispatchFn = async (capability, task, signal) => {
    const definition = this.registry.resolve(capability);
    if (!definition) {
      // 未注册能力：让 Planner 收到明确错误并换路（工具 execute throw 时以 isError 交还模型）
      throw new Error(`no worker registered for capability: ${capability}`);
    }
    const runtime = definition.runtimeFactory();
    const result = await runtime.run(task, signal);
    return parseWorkerResult(result);
  };
}
