// system-prompt 测试 — 锁定 ② 修复：能力清单由 Registry 动态生成（不再硬编码）。

import { buildPlannerSystemPrompt } from '@/agents/planner/system-prompt';

const ctx = {
  planId: 'plan-1',
  runId: 'run-1',
  attempt: 0,
  objective: 'XX 区域火灾侦察',
  maxTurns: 8,
  timeoutMs: 120_000,
};

describe('buildPlannerSystemPrompt — 动态能力清单（修复②）', () => {
  it('渲染传入的能力清单（capability + 描述）', () => {
    const prompt = buildPlannerSystemPrompt(ctx, [
      { capability: 'allocation.assign', description: '任务分配' },
      { capability: 'risk.assess', description: '风险评估' },
    ]);
    expect(prompt).toContain('- allocation.assign：任务分配');
    expect(prompt).toContain('- risk.assess：风险评估');
  });

  it('能力清单为空时给出占位说明（不硬编码任何能力）', () => {
    const prompt = buildPlannerSystemPrompt(ctx);
    expect(prompt).toContain('暂无已注册能力');
    expect(prompt).not.toContain('allocation.assign');
  });

  it('渲染运行上下文参数', () => {
    const prompt = buildPlannerSystemPrompt(ctx, []);
    expect(prompt).toContain('planId=plan-1');
    expect(prompt).toContain('runId=run-1');
    expect(prompt).toContain('maxTurns=8');
  });
});
