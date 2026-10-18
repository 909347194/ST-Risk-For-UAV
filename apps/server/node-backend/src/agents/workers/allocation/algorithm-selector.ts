// 算法选择器 — Worker 内部的"算法工具"决策（不是 Agent）。
// Hungarian：精确、适合中小规模指派；Auction/DE/ALNS 等按规模与约束后续接入。
// 选择逻辑是确定性规则，禁止让 LLM 参与选算法（结果必须可复现）。

export type AllocationAlgorithm = 'hungarian' | 'auction';

export interface AlgorithmSelectionInput {
  /** 任务规模（任务数 × 无人机数，用于复杂度判断）。 */
  taskCount?: number;
  uavCount?: number;
  /** 显式指定（Planner 工具可传 algorithm 参数透传）。 */
  requested?: string;
}

export function selectAllocationAlgorithm(input: AlgorithmSelectionInput): AllocationAlgorithm {
  if (input.requested === 'hungarian' || input.requested === 'auction') {
    return input.requested;
  }
  // TODO Phase 2：按规模/约束的决策规则（如大规模 → auction，含优先级 → DE）
  return 'hungarian';
}
