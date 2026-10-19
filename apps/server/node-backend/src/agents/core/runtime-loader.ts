// ESM 惰性加载器 — 解决 "pi-agent-core / pi-ai 是 ESM-only，而 node-backend 当前为 CommonJS 构建" 的约束。
//
// 背景：本项目 tsconfig 使用 `module: commonjs`，TypeScript 会把顶层 `import()` 降级为
// `require('...')`。而 pi-agent-core / pi-ai 只发布 ESM（"type": "module"，无 CJS 构建），
// 在 CommonJS 下 `require()` 会抛 ERR_REQUIRE_ESM。
//
// 解决：用间接 `import()`（放在 `new Function` 字符串体内，TS 不会降级）触发 Node 原生的
// 动态 ESM import。这是 Phase 1 的最小改动方案；第五阶段工程化时再把整个 node-backend 转 ESM。
//
// 类型层面（`import type`）是擦除的，不影响运行期；这里只把"运行时值"（Agent / Type /
// createModels 等）通过动态加载取出，避免任何静态 ESM import 进入 CommonJS 产物。

import type { AgentTool, AgentToolResult, StreamFn } from '@earendil-works/pi-agent-core';
import type { Model, Models, SimpleStreamOptions } from '@earendil-works/pi-ai';

/** 仅类型：pi-agent-core 的模块命名空间（编译期擦除，不产生运行时依赖）。 */
export type PiAgentCore = typeof import('@earendil-works/pi-agent-core');
/** 仅类型：pi-ai 的模块命名空间（编译期擦除，不产生运行时依赖）。 */
export type PiAi = typeof import('@earendil-works/pi-ai');

// 间接动态 import：函数体是字符串，TS 不会把它降级为 require()。
const dynamicImport = new Function('specifier', 'return import(specifier)') as (
  specifier: string,
) => Promise<any>;

/** 加载 pi-agent-core 命名空间（Agent / AgentHarness 等）。 */
export async function loadPiAgentCore(): Promise<PiAgentCore> {
  return dynamicImport('@earendil-works/pi-agent-core') as Promise<PiAgentCore>;
}

/** 加载 pi-ai 命名空间（Type / createModels / ModelsError 等）。 */
export async function loadPiAi(): Promise<PiAi> {
  return dynamicImport('@earendil-works/pi-ai') as Promise<PiAi>;
}

/**
 * 加载 pi-ai 的 provider 子模块（如 `@earendil-works/pi-ai/providers/deepseek`）。
 * 子路径同样是 ESM-only，必须动态 import；模块内取 `<name>Provider()` 工厂。
 */
export async function loadPiProviderModule(provider: string): Promise<Record<string, unknown>> {
  return dynamicImport(`@earendil-works/pi-ai/providers/${provider}`) as Promise<Record<string, unknown>>;
}

/** 并行加载两个命名空间。 */
export async function loadPiRuntime(): Promise<{ core: PiAgentCore; ai: PiAi }> {
  const [core, ai] = await Promise.all([loadPiAgentCore(), loadPiAi()]);
  return { core, ai };
}

/**
 * 用 pi-ai 的 `Models` 实例构造 pi-agent-core 所需的 `StreamFn`。
 * Agent 的工具调用循环会把归一化后的 `TranscriptContext` 交给这个 streamFn。
 */
export function createStreamFn(models: Models): StreamFn {
  return (model, context, options) =>
    models.streamSimple(model as Model<any>, context, options as SimpleStreamOptions);
}

// 仅用于类型推导的再导出，避免调用方重复写 `import type`。
export type { AgentTool, AgentToolResult, StreamFn };
