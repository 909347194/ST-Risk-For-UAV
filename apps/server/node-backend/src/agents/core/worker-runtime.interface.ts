// Worker 运行时统一接口 — Worker = 领域能力，不是算法（见 ARCHITECTURE.md 关键设计要点 3）
//
// LLM 型 Worker（Agent）与确定型 Worker（纯计算/调 Python/规则）都实现本接口，
// 从而被 WorkerRouter 以同一 Contract 调用。V1 全部为确定型执行器，只有 Planner 用 LLM。

import type { WorkerTask } from '@/contracts/worker-task';
import type { WorkerResult } from '@/contracts/worker-result';

/** Worker 运行时：吃 WorkerTask，吐 WorkerResult。失败按契约表达（status/feedback/error），不随意 throw。 */
export interface WorkerRuntime {
  run(task: WorkerTask, signal?: AbortSignal): Promise<WorkerResult>;
}

/** Worker 注册定义：capability → 实现。由 registry/definitions/*.ts 静态注册。 */
export interface WorkerDefinition {
  /** 能力标识，如 allocation.assign（解耦键：请求方与实现方互不知道对方）。 */
  capability: string;
  /** 执行者类型，如 allocation-worker（写入 WorkerResult.workerType）。 */
  workerType: string;
  /** 能力描述（给人看；工具描述给模型看）。 */
  description: string;
  /** 运行时工厂：每次派发取/建实例。 */
  runtimeFactory: () => WorkerRuntime;
}
