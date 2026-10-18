// A2A Contract — WorkerTask
// 设计定稿中的统一任务对象。Planner 通过工具把模型参数包成 WorkerTask，经 Router 分发给 Worker。
// 这里只放类型与常量；每个领域的强类型 input/output 在各自 Worker 模块内定义。

export type WorkerStatus = 'success' | 'partial' | 'failed' | 'need_input';

export type FeedbackType =
  | 'replan'
  | 'reallocate'
  | 'reroute'
  | 'reassess_risk'
  | 'need_information'
  | 'none';

export interface WorkerTask<TInput = unknown> {
  /** 本次工具调用的唯一 ID（由 Planner/Orchestrator 生成）。 */
  taskId: string;
  /** 所属调度计划 ID。 */
  planId: string;
  /** 本次执行 Run ID。 */
  runId: string;
  /** 执行者类型，如 allocation-worker / risk-worker。 */
  workerType: string;
  /** 能力标识，如 allocation.assign / risk.assess（Planner 优先按能力请求）。 */
  capability: string;
  /** 任务目标描述，供 Worker 理解意图。 */
  objective: string;
  /** 领域输入（由模型/Orchestrator 提供，运行期需用 zod 校验）。 */
  input: TInput;
  /** 第几次尝试（用于重试与反馈闭环）。 */
  attempt: number;
  /** Contract 版本，随 schema 演进递增。 */
  schemaVersion: string;
}
