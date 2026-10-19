// 执行策略 = pi 的 `beforeToolCall` 钩子（见 docs/architecture/agent-architecture-node-landing.md 第 7.3 节）。
//
// 遵循 pi：不自研"工具拦截框架"，策略的执行点就是 Agent 的 beforeToolCall——
// pi 在工具参数按 TypeBox 校验通过后调用它，返回 { block, reason, terminate } 即可拦下工具调用
// （运行时以错误工具结果交还模型）。重试上限/取消/权限三类策略在这里收敛。
//
// 本文件只用 `import type` 引 pi 类型，无运行时 ESM 依赖。

import type { BeforeToolCallContext, BeforeToolCallResult } from '@earendil-works/pi-agent-core';

/** 可选的计时登记（与 feedback-handler 的 ToolExecutionTracker 配合算 durationMs）。 */
export interface ToolCallTracker {
  start(toolCallId: string): void;
}

/**
 * 执行策略默认值（唯一收敛点，不再散落内联在各装配处）。
 * 可被调用方覆盖；后续可接 env/配置中心。
 */
export const EXECUTION_POLICY_DEFAULTS = {
  /** 单个工具的最大调用次数（含重试）。 */
  maxCallsPerTool: 3,
  /** Replanner 否决线：最大决策轮次（finishTurn maxTurns）。 */
  maxTurns: 8,
  /** Run 硬超时（毫秒；超时降级人工接管）。 */
  timeoutMs: 120_000,
} as const;

export interface ExecutionPolicyOptions {
  /** Run 是否已取消（如人工中止）。true → block + terminate（整批全 terminate 才停轮）。 */
  isRunCancelled?: () => Promise<boolean> | boolean;
  /** 工具准入（能力白名单/权限）。false → block。 */
  allowTool?: (toolName: string) => boolean;
  /** 单个工具的最大调用次数（含重试）。超过 → block + terminate，防止模型无限重试。 */
  maxCallsPerTool?: number;
  /** 可选：工具真正执行前登记开始时间。 */
  tracker?: ToolCallTracker;
}

/**
 * 构造 pi `beforeToolCall` 钩子（执行策略门）。
 * 返回 undefined = 放行；返回 { block: true } = 拦下并以错误工具结果回给模型。
 */
export function createBeforeToolCallHook(
  options: ExecutionPolicyOptions = {},
): (context: BeforeToolCallContext, signal?: AbortSignal) => Promise<BeforeToolCallResult | undefined> {
  const callCounts = new Map<string, number>();

  return async ({ toolCall }: BeforeToolCallContext): Promise<BeforeToolCallResult | undefined> => {
    if (options.isRunCancelled && (await options.isRunCancelled())) {
      return { block: true, reason: 'run cancelled', terminate: true };
    }
    if (options.allowTool && !options.allowTool(toolCall.name)) {
      return { block: true, reason: `tool not permitted: ${toolCall.name}` };
    }
    const count = (callCounts.get(toolCall.name) ?? 0) + 1;
    callCounts.set(toolCall.name, count);
    if (options.maxCallsPerTool && count > options.maxCallsPerTool) {
      return {
        block: true,
        reason: `retry limit reached for ${toolCall.name} (max ${options.maxCallsPerTool})`,
        terminate: true,
      };
    }
    // 放行后登记开始时间（block 的调用不会执行，也不该计时）。
    options.tracker?.start(toolCall.id);
    return undefined;
  };
}
