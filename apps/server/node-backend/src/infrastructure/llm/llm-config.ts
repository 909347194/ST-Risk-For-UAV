// LLM 配置 — pi-ai 的 Models/Model 装配（见 agent-architecture-node-landing.md §2.1 约定 #2/#10）。
//
// pi 约定：
//  - `createModels()` + `models.setProvider(xxxProvider())` + `models.getModel(provider, id)`；
//  - 鉴权由 Provider 自行解析（环境变量 / CredentialStore / OAuth）；Agent 的 getApiKey 只用于动态 token；
//  - provider 子路径（@earendil-works/pi-ai/providers/*）也是 ESM-only，必须经 runtime-loader 动态 import。

import type { Model, Models } from '@earendil-works/pi-ai';
import { loadPiRuntime } from '@/agents/core/runtime-loader';

export interface LlmConfig {
  /** Provider 标识，如 anthropic / openai / gemini。 */
  provider: string;
  /** 模型 ID，如 claude-sonnet-4-6。 */
  modelId: string;
}

export interface PlannerModelHandle {
  models: Models;
  model: Model<any>;
}

/**
 * 构造 Planner 用的 Models + Model。
 * 骨架：provider 工厂动态注册待 Phase 1 接入（每个 provider 的工厂名不同，
 * 通用做法是 import `@earendil-works/pi-ai/providers/<provider>` 后取其 `*Provider` 导出）。
 */
export async function createPlannerModel(config: LlmConfig): Promise<PlannerModelHandle> {
  const { ai } = await loadPiRuntime();
  const models = ai.createModels();

  // TODO Phase 1：动态 import provider 模块并注册：
  //   const mod = await dynamicImport(`@earendil-works/pi-ai/providers/${config.provider}`);
  //   models.setProvider(mod[`${config.provider}Provider`]());
  throw new Error(`not implemented: provider registration for '${config.provider}' (Phase 1)`);
}
