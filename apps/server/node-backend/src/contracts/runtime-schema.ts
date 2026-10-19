// Contract 边界运行时校验（zod）— 见 docs/architecture/agent-architecture-node-landing.md §6.2
//
// 分工：TypeBox 管工具参数（pi 运行时自动校验）；zod 只在 pi 之外的边界兜底：
//   ① WorkerRuntime 返回的 WorkerResult（Router 回收时校验）
//   ② Python 服务响应（AlgorithmClient 回收时校验）
//   ③ 模型/Orchestrator 构造 WorkerTask 时的领域 input 兜底
//
// schema 真相源在 contracts/worker-task.ts / worker-result.ts（TS 类型由 schema 推导，单源无漂移）；
// 本文件只提供解析入口与统一导出面。

import { workerTaskSchema } from './worker-task';
import { workerResultSchema } from './worker-result';
import type { WorkerTask } from './worker-task';
import type { WorkerResult } from './worker-result';

export { feedbackTypeSchema, workerStatusSchema, workerTaskSchema } from './worker-task';
export { workerResultSchema } from './worker-result';
export type { WorkerStatus, FeedbackType, WorkerTask } from './worker-task';
export type { WorkerResult } from './worker-result';

/** 校验并归一 WorkerResult；失败抛 zod 错误（在 Router/Orchestrator 边界炸掉，别把脏数据传给 Planner）。 */
export function parseWorkerResult(value: unknown): WorkerResult {
  return workerResultSchema.parse(value) as WorkerResult;
}

/** 校验 WorkerTask；在 dispatch 分发前调用。 */
export function parseWorkerTask(value: unknown): WorkerTask {
  return workerTaskSchema.parse(value) as WorkerTask;
}
