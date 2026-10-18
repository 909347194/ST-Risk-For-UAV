// Replanner = pi 的 `finishTurn` 钩子（见 docs/architecture/agent-architecture-node-landing.md 第 7.1 节）。
//
// 遵循 pi：「重分配/重规划/重试/结束」的决策点就是 finishTurn 的 { action: 'continue' | 'end' }，
// 不自研轮次调度器：
//  - 返回 undefined      → 保留 pi 正常调度（有工具结果/队列消息时循环自然继续）
//  - { action: 'continue' } → 强制补一轮请求（⚠️ 无条件返回会死循环，必须有收敛条件）
//  - { action: 'end' }      → turn_end 后结束本轮 run
//
// 本文件只 `import type` 引 pi 类型，无运行时 ESM 依赖。

import type { AgentTurnContext, AgentTurnDecision, FinishTurn } from '@earendil-works/pi-agent-core';

export interface ReplannerOptions {
  /** 收敛条件：最大决策轮次，达到即 { action: 'end' }。防 finishTurn 无限 continue。 */
  maxTurns?: number;
  /**
   * 自定义"是否再补一轮"判定（如综合 WorkerResult.feedback 决定重规划）。
   * 返回 true → { action: 'continue' }；返回 false → { action: 'end' }；未配置则保持 pi 正常调度。
   */
  shouldContinue?: (turn: AgentTurnContext, signal?: AbortSignal) => Promise<boolean> | boolean;
}

/**
 * 构造 pi `finishTurn` 钩子（Replanner 决策）。
 * 按 pi README 约定：先守卫 error/aborted（硬退出，不干预决策）。
 */
export function createFinishTurnHook(
  options: ReplannerOptions = {},
): FinishTurn {
  let turns = 0;

  return async (turn: AgentTurnContext, signal?: AbortSignal): Promise<AgentTurnDecision | undefined> => {
    // error / aborted 是 pi 的硬退出：决策被忽略，必须先守卫（含副作用的判定尤其重要）。
    if (turn.message.stopReason === 'error' || turn.message.stopReason === 'aborted') {
      return undefined;
    }

    turns += 1;

    if (options.maxTurns !== undefined && turns >= options.maxTurns) {
      return { action: 'end' };
    }

    if (options.shouldContinue) {
      return (await options.shouldContinue(turn, signal)) ? { action: 'continue' } : { action: 'end' };
    }

    // 未配置判定：保持 pi 正常调度（工具结果/队列消息决定是否继续）。
    return undefined;
  };
}
