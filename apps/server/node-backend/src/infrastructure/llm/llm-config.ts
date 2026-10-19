// LLM 配置 — pi-ai 的 Models/Model 装配（见 agent-architecture-node-landing.md §2.1 约定 #2/#10）。
//
// 当前选型（2026-10-19 定稿）：DeepSeek `deepseek-flash`（pi-ai 模型目录内建，api=openai-completions）。
// pi 约定：
//  - `createModels()` + `models.setProvider(deepseekProvider())` + `models.getModel('deepseek', 'deepseek-flash')`；
//  - 鉴权由 Provider 自行解析：DeepSeek 走环境变量 **DEEPSEEK_API_KEY**（envApiKeyAuth），key 不进代码/配置；
//  - provider 子路径（@earendil-works/pi-ai/providers/*）也是 ESM-only，必须经 runtime-loader 动态 import；
//  - Agent 的 getApiKey 只用于动态/易过期 token，DeepSeek 静态 key 用不到它。

import type { Model, Models } from '@earendil-works/pi-ai';
import { loadPiProviderModule, loadPiRuntime } from '@/agents/core/runtime-loader';

export interface LlmConfig {
  /** Provider 标识（pi-ai KnownProvider，如 deepseek）。 */
  provider: string;
  /** 模型 ID（pi-ai 模型目录内必须存在）。 */
  modelId: string;
}

/**
 * 当前默认选型：DeepSeek deepseek-flash。
 * 可用 LLM_PROVIDER / LLM_MODEL_ID 环境变量整体替换（如换 deepseek-v4-pro）。
 *
 * 注意（pi 目录元数据）：deepseek-flash 的 thinkingLevelMap 为
 * minimal→null / low→low / medium→null / high→high / max→max；
 * 需要推理时建议 thinkingLevel 取 'low' | 'high' | 'max'，别取 medium。
 */
export const DEFAULT_LLM_CONFIG: LlmConfig = {
  provider: process.env.LLM_PROVIDER || 'deepseek',
  modelId: process.env.LLM_MODEL_ID || 'deepseek-flash',
};

export interface PlannerModelHandle {
  models: Models;
  model: Model<any>;
}

/**
 * 构造 Planner 用的 Models + Model。
 * 鉴权预检：DEEPSEEK_API_KEY 未配置时给出明确错误（而不是跑到第一轮 LLM 调用才炸）。
 */
export async function createPlannerModel(
  config: LlmConfig = DEFAULT_LLM_CONFIG,
): Promise<PlannerModelHandle> {
  const { ai } = await loadPiRuntime();
  const models = ai.createModels();

  // provider 工厂动态注册（ESM 子路径）：模块导出 `<provider>Provider()`，如 deepseekProvider()
  const providerModule = await loadPiProviderModule(config.provider);
  const factoryName = `${config.provider}Provider`;
  const factory = (providerModule[factoryName] ?? providerModule.default) as (() => unknown) | undefined;
  if (typeof factory !== 'function') {
    throw new Error(`provider factory not found: ${factoryName} in @earendil-works/pi-ai/providers/${config.provider}`);
  }
  models.setProvider(factory() as never);

  // 鉴权预检（pi 的 getAuth：解析 env/凭证，未配置返回 undefined）
  const auth = await models.getAuth(config.provider);
  if (!auth) {
    throw new Error(
      `LLM auth not configured for provider '${config.provider}' — set DEEPSEEK_API_KEY (环境变量) first`,
    );
  }

  // 模型必须在 pi-ai 目录内（deepseek-flash 在册）
  const model = models.getModel(config.provider, config.modelId);
  if (!model) {
    throw new Error(`model not found in pi catalog: ${config.provider}/${config.modelId}`);
  }

  return { models, model };
}
