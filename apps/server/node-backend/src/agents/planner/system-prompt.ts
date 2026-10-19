// Planner 系统提示词 — 能力清单由 Registry 动态生成（不再硬编码，避免与注册表双份维护）。
//
// pi 约定：改提示词不重建 Agent——用 system message 的 content 增量 / sections 命名替换动态更新。
// 本文件产出初始 systemPrompt；运行中能力变化可走 sections（后续 Orchestrator 接入）。

import type { PlannerRunContext } from '@/agents/core/planner-context';

/** 提示词需要的能力信息（WorkerRegistry.list() 的最小视图，避免反向依赖）。 */
export interface PromptCapability {
  capability: string;
  description: string;
}

export function buildPlannerSystemPrompt(
  ctx: PlannerRunContext,
  capabilities: PromptCapability[] = [],
): string {
  const capabilityLines = capabilities.length
    ? capabilities.map((c) => `- ${c.capability}：${c.description}`)
    : ['- （暂无已注册能力，等待 Registry 装配）'];

  return [
    '# 角色',
    '你是多警种无人机智能调度系统的调度 Planner：负责理解调度意图、拆解任务、',
    '通过工具委派专业 Worker 执行，并综合结果给出调度方案。',
    '',
    '# 职责边界（必须遵守）',
    '- 你只做决策与编排，不做数值优化：分配/航线/风险等一律委派对应能力工具。',
    '- 最终方案必须经 validation 能力确定性校验通过后才可下发；校验不过不得绕过。',
    '- 参数不确定时宁可少做、问清楚（触发 need_input），不要编造输入。',
    '',
    '# 可用能力',
    ...capabilityLines,
    '',
    '# 输出约定',
    '- 工具结果为结构化 JSON；基于事实汇总，明确标注未分配/冲突/超限项。',
    '',
    '# 当前运行（内部参数，不对外复述）',
    `- planId=${ctx.planId} runId=${ctx.runId} attempt=${ctx.attempt} maxTurns=${ctx.maxTurns}`,
  ].join('\n');
}
