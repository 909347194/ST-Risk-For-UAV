// validation 硬闸门 — 最终方案的确定性校验（见 agent-architecture-node-landing.md §13「四样兑底」之一）。
//
// 定调：**不信任 Planner 输出**。LLM 产出的分配方案必须过本闸门（纯确定性规则，无 LLM 参与），
// 不过 → Run 置 FAILED，不得绕过置 COMPLETED。这是 prompt 注入面与模型幻觉的结构性兑底。
//
// 校验对象 = 分配方案（与 Python AllocateTasksResponse 对齐，见 services/python/python-client.ts）；
// 请求侧事实（uavIds/taskIds，来自 assign_tasks 工具入参）可选传入做交叉校验。

/** 分配方案（AllocateTasksResponse 形状）。 */
export interface FinalPlan {
  allocations: Array<{ uav_id: string; task_id: string; estimated_cost?: number }>;
  unassigned_tasks: string[];
  algorithm_used?: string;
}

/** 请求侧事实（assign_tasks 工具入参的请求集合）。 */
export interface PlanRequest {
  uavIds: string[];
  taskIds: string[];
}

export interface FinalPlanCandidate {
  /** 请求侧事实；缺省时只做方案内部一致性校验。 */
  request?: PlanRequest;
  plan: FinalPlan;
}

export interface ValidationResult {
  valid: boolean;
  violations: string[];
}

/**
 * 确定性校验最终方案。返回全部违规项（不短路），供落库复盘。
 *
 * 校验规则：
 *  ① 结构：allocations / unassigned_tasks 必须是数组，条目字段类型正确；
 *  ② 任务不重复分配（一把任务只能落一架无人机）；
 *  ③ 已分配与未分配不相交（同一任务不能既分配又未分配）；
 *  ④ 请求侧交叉（有 request 时）：无人机必须来自请求集合、任务集合必须与请求完全一致（无丢失、无幻影）。
 */
export function validateFinalPlan(candidate: FinalPlanCandidate): ValidationResult {
  const violations: string[] = [];
  const { plan, request } = candidate;

  // ① 结构校验
  if (!plan || !Array.isArray(plan.allocations) || !Array.isArray(plan.unassigned_tasks)) {
    return { valid: false, violations: ['plan shape invalid: allocations/unassigned_tasks must be arrays'] };
  }

  // ② 任务不重复分配
  const assigned = new Set<string>();
  for (const entry of plan.allocations) {
    if (!entry || typeof entry.task_id !== 'string' || typeof entry.uav_id !== 'string') {
      violations.push('allocation entry invalid: uav_id/task_id must be strings');
      continue;
    }
    if (assigned.has(entry.task_id)) {
      violations.push(`task assigned more than once: ${entry.task_id}`);
    }
    assigned.add(entry.task_id);
  }

  // ③ 已分配与未分配不相交
  const unassigned = new Set(plan.unassigned_tasks);
  for (const taskId of assigned) {
    if (unassigned.has(taskId)) {
      violations.push(`task both assigned and unassigned: ${taskId}`);
    }
  }

  // ④ 请求侧交叉校验
  if (request) {
    const uavSet = new Set(request.uavIds);
    for (const entry of plan.allocations) {
      if (typeof entry?.uav_id === 'string' && !uavSet.has(entry.uav_id)) {
        violations.push(`unknown uav in allocation: ${entry.uav_id}`);
      }
    }
    const requested = new Set(request.taskIds);
    const accounted = new Set([...assigned, ...unassigned]);
    for (const taskId of requested) {
      if (!accounted.has(taskId)) {
        violations.push(`requested task missing from plan: ${taskId}`);
      }
    }
    for (const taskId of accounted) {
      if (!requested.has(taskId)) {
        violations.push(`phantom task in plan: ${taskId}`);
      }
    }
  }

  return { valid: violations.length === 0, violations };
}

/** 工具调用记录（Orchestrator 经 afterToolCall 钩子收集；结构化窄接口，不依赖 pi 类型）。 */
export interface ToolCallRecord {
  toolName: string;
  args: unknown;
  result: { status: string; result?: unknown };
}

/**
 * 从工具调用记录提取最终方案候选：取**最后一次**成功的 assign_tasks 调用
 * （success / partial 均带方案；partial 的未分配项由闸门规则 ④ 兜住）。
 */
export function extractFinalPlan(records: ToolCallRecord[]): FinalPlanCandidate | undefined {
  for (let i = records.length - 1; i >= 0; i--) {
    const record = records[i];
    if (record.toolName !== 'assign_tasks') continue;
    if (record.result.status !== 'success' && record.result.status !== 'partial') continue;
    const args = (record.args ?? {}) as Partial<PlanRequest>;
    return {
      request:
        Array.isArray(args.uavIds) && Array.isArray(args.taskIds)
          ? { uavIds: args.uavIds, taskIds: args.taskIds }
          : undefined,
      plan: record.result.result as FinalPlan,
    };
  }
  return undefined;
}
