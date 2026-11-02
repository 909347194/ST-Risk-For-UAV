// validation 硬闸门单测 — 纯确定性规则，无 LLM/DB 依赖。

import {
  extractFinalPlan,
  validateFinalPlan,
  type FinalPlan,
  type ToolCallRecord,
} from '@/orchestration/validation-gate';

function plan(patch: Partial<FinalPlan> = {}): FinalPlan {
  return {
    allocations: [
      { uav_id: 'uav-1', task_id: 'task-1', estimated_cost: 10 },
      { uav_id: 'uav-2', task_id: 'task-2', estimated_cost: 12 },
    ],
    unassigned_tasks: [],
    algorithm_used: 'hungarian',
    ...patch,
  };
}

describe('validateFinalPlan — validation 硬闸门', () => {
  it('合法方案（全覆盖）→ valid', () => {
    const result = validateFinalPlan({
      plan: plan(),
      request: { uavIds: ['uav-1', 'uav-2'], taskIds: ['task-1', 'task-2'] },
    });
    expect(result.valid).toBe(true);
    expect(result.violations).toEqual([]);
  });

  it('合法方案（部分未分配，且与请求集合一致）→ valid', () => {
    const result = validateFinalPlan({
      plan: plan({ allocations: [{ uav_id: 'uav-1', task_id: 'task-1' }], unassigned_tasks: ['task-2'] }),
      request: { uavIds: ['uav-1', 'uav-2'], taskIds: ['task-1', 'task-2'] },
    });
    expect(result.valid).toBe(true);
  });

  it('任务重复分配 → invalid', () => {
    const result = validateFinalPlan({
      plan: plan({
        allocations: [
          { uav_id: 'uav-1', task_id: 'task-1' },
          { uav_id: 'uav-2', task_id: 'task-1' },
        ],
      }),
    });
    expect(result.valid).toBe(false);
    expect(result.violations).toContain('task assigned more than once: task-1');
  });

  it('同一任务既分配又未分配 → invalid', () => {
    const result = validateFinalPlan({
      plan: plan({ unassigned_tasks: ['task-1'] }),
    });
    expect(result.valid).toBe(false);
    expect(result.violations).toContain('task both assigned and unassigned: task-1');
  });

  it('请求集合外的无人机 → invalid（unknown uav）', () => {
    const result = validateFinalPlan({
      plan: plan({ allocations: [{ uav_id: 'uav-9', task_id: 'task-1' }] }),
      request: { uavIds: ['uav-1', 'uav-2'], taskIds: ['task-1', 'task-2'] },
    });
    expect(result.valid).toBe(false);
    expect(result.violations).toContain('unknown uav in allocation: uav-9');
  });

  it('请求任务在方案中丢失 → invalid（missing）', () => {
    const result = validateFinalPlan({
      plan: plan({ allocations: [{ uav_id: 'uav-1', task_id: 'task-1' }], unassigned_tasks: [] }),
      request: { uavIds: ['uav-1', 'uav-2'], taskIds: ['task-1', 'task-2'] },
    });
    expect(result.valid).toBe(false);
    expect(result.violations).toContain('requested task missing from plan: task-2');
  });

  it('方案出现请求外的幻影任务 → invalid（phantom）', () => {
    const result = validateFinalPlan({
      plan: plan({ allocations: [{ uav_id: 'uav-1', task_id: 'task-99' }], unassigned_tasks: [] }),
      request: { uavIds: ['uav-1'], taskIds: ['task-1'] },
    });
    expect(result.valid).toBe(false);
    expect(result.violations).toContain('phantom task in plan: task-99');
  });

  it('结构非法（allocations 非数组）→ invalid 且不抛异常', () => {
    const result = validateFinalPlan({
      plan: { allocations: 'nope', unassigned_tasks: [] } as unknown as FinalPlan,
    });
    expect(result.valid).toBe(false);
    expect(result.violations[0]).toContain('plan shape invalid');
  });

  it('无 request 时只做内部一致性校验（合法方案通过）', () => {
    const result = validateFinalPlan({ plan: plan() });
    expect(result.valid).toBe(true);
  });

  it('违规不短路：多个违规一次性全部返回', () => {
    const result = validateFinalPlan({
      plan: plan({
        allocations: [
          { uav_id: 'uav-1', task_id: 'task-1' },
          { uav_id: 'uav-2', task_id: 'task-1' },
        ],
        unassigned_tasks: ['task-1'],
      }),
    });
    expect(result.violations.length).toBeGreaterThanOrEqual(2);
  });
});

describe('extractFinalPlan — 从工具调用记录提取最终方案', () => {
  function record(patch: Partial<ToolCallRecord> = {}): ToolCallRecord {
    return {
      toolName: 'assign_tasks',
      args: { uavIds: ['uav-1'], taskIds: ['task-1'] },
      result: { status: 'success', result: plan({ allocations: [{ uav_id: 'uav-1', task_id: 'task-1' }] }) },
      ...patch,
    };
  }

  it('取最后一次成功的 assign_tasks（含请求侧事实）', () => {
    const candidate = extractFinalPlan([
      record({ result: { status: 'success', result: plan({ allocations: [] }) } }),
      record(),
    ]);
    expect(candidate).toBeDefined();
    expect(candidate?.request).toEqual({ uavIds: ['uav-1'], taskIds: ['task-1'] });
    expect(candidate?.plan.allocations).toHaveLength(1);
  });

  it('failed 调用被跳过', () => {
    const candidate = extractFinalPlan([
      record({ result: { status: 'failed', result: undefined } }),
    ]);
    expect(candidate).toBeUndefined();
  });

  it('partial 状态也带方案（未分配项由闸门规则兜住）', () => {
    const candidate = extractFinalPlan([
      record({
        result: {
          status: 'partial',
          result: plan({ allocations: [], unassigned_tasks: ['task-1'] }),
        },
      }),
    ]);
    expect(candidate).toBeDefined();
    expect(candidate?.plan.unassigned_tasks).toEqual(['task-1']);
  });

  it('无 assign_tasks 记录 → undefined', () => {
    expect(extractFinalPlan([record({ toolName: 'other_tool' })])).toBeUndefined();
    expect(extractFinalPlan([])).toBeUndefined();
  });

  it('args 缺 uavIds/taskIds → request 为 undefined（降级为内部一致性校验）', () => {
    const candidate = extractFinalPlan([record({ args: {} })]);
    expect(candidate?.request).toBeUndefined();
  });
});
