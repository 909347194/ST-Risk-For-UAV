// Run 事件总线 — Planner 闭环事件 → SSE 推流（前端可见）。
//
// 背景（2026-10-28）：pi 官方（@earendil-works/pi-agent-core 1.4.x）只提供进程内
// agent.subscribe() pub/sub 与浏览器端 streamProxy，没有服务端推流原语；harness/session
// 是持久化、Transport 是上游 LLM 传输。故推流层按 NestJS 主流方案自建：@Sse() + RxJS，
// 事件源即编排器已在用的 subscribe 流（本总线只做 fan-out，不新增事件来源）。
//
// 语义：
//   - publish()：编排器在事件监听/生命周期处调用；写入 ReplaySubject（回放缓冲 + fan-out 二合一）。
//   - stream()：SSE 端点订阅。ReplaySubject 自动回放历史（前端晚到也能看全程）再接实时流；
//     run_end 后 complete（SSE 连接关闭），已终态且已清理的 run 直接空流关闭。
//   - 多订阅者安全：同一 runId 多个浏览器标签订阅同一 ReplaySubject，各自独立收到全量事件。
//   - 内存治理：缓冲上限 500 条（ReplaySubject 自动淘汰最旧的）；run_end 后 60s 清理
//     （settled 标记保留，迟到的连接空流关闭，不挂住）。

import { Injectable } from '@nestjs/common';
import { of, type Observable, ReplaySubject } from 'rxjs';

/** 推流事件契约（SSE data 负载，JSON 序列化后到前端）。 */
export interface RunStreamEvent {
  /** run_start / agent_start / turn_start / turn_end / message_end / tool_execution_start / tool_execution_end / agent_end / run_end */
  type: string;
  runId: string;
  /** ISO 时间戳（事件产生时刻）。 */
  timestamp: string;
  /** 事件载荷：pi AgentEvent 原文或生命周期信息（如 run_end 带 DispatchOutcome）。 */
  data?: unknown;
}

@Injectable()
export class RunEventBus {
  private static readonly BUFFER_SIZE = 500;
  private static readonly CLEANUP_DELAY_MS = 60_000;

  /** runId → 回放+实时流（ReplaySubject：晚到订阅者自动补发历史，上限 500 条）。 */
  private readonly streams = new Map<string, ReplaySubject<RunStreamEvent>>();
  /** 已终态的 runId（保留，避免清理后迟到连接挂住）。 */
  private readonly settled = new Set<string>();
  private readonly cleanupTimers = new Map<string, ReturnType<typeof setTimeout>>();

  /** 发布一个事件（编排器调用；同步内存操作，不抛异常）。 */
  publish(runId: string, event: { type: string; data?: unknown }): void {
    const full: RunStreamEvent = {
      type: event.type,
      runId,
      timestamp: new Date().toISOString(),
      ...(event.data !== undefined ? { data: event.data } : {}),
    };

    this.subjectFor(runId).next(full);

    if (event.type === 'run_end') {
      this.settled.add(runId);
      this.streams.get(runId)?.complete();
      this.scheduleCleanup(runId);
    }
  }

  /** 订阅一个 run 的事件流：自动回放历史 + 实时流；终态后自动关闭。 */
  stream(runId: string): Observable<RunStreamEvent> {
    // 已终态且已清理（60s 后）：空流直接关闭，避免前端挂住
    if (this.settled.has(runId) && !this.streams.has(runId)) {
      return of<RunStreamEvent>();
    }
    return this.subjectFor(runId).asObservable();
  }

  private subjectFor(runId: string): ReplaySubject<RunStreamEvent> {
    let subject = this.streams.get(runId);
    if (!subject) {
      subject = new ReplaySubject<RunStreamEvent>(RunEventBus.BUFFER_SIZE);
      this.streams.set(runId, subject);
    }
    return subject;
  }

  /** run_end 后延迟清理流缓冲（settled 标记保留）。 */
  private scheduleCleanup(runId: string): void {
    if (this.cleanupTimers.has(runId)) return;
    const timer = setTimeout(() => {
      this.streams.delete(runId);
      this.cleanupTimers.delete(runId);
    }, RunEventBus.CLEANUP_DELAY_MS);
    timer.unref?.();
    this.cleanupTimers.set(runId, timer);
  }
}
