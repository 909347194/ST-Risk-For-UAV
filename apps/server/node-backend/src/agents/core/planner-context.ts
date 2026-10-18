// Planner 运行上下文 — 一次调度认知的控制参数（预算/安全类约束）。
// 与 Replanner 的定调一致：这些是"刹车"参数（否决用），不是正向调度指令；正向决策归 Planner。

export interface PlannerRunContext {
  /** 所属调度计划 ID。 */
  planId: string;
  /** 本次执行 Run ID。 */
  runId: string;
  /** 第几次尝试（重规划/重试递增）。 */
  attempt: number;
  /** 调度意图（人类语言，如"XX 区域火灾侦察"）。 */
  objective: string;
  /** 最大决策轮次（Replanner 否决线：finishTurn maxTurns）。 */
  maxTurns: number;
  /** Run 硬超时（毫秒；超时降级人工接管，agent.abort()）。 */
  timeoutMs: number;
}
