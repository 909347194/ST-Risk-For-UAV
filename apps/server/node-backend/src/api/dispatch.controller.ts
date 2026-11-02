// 调度 API — 对外 HTTP 入口（旧 modules/agent/agent.controller.ts 占位已于 2026-10-28 拆除）。
// 本控制器只做"收单 → 交给 PlannerOrchestrator + SSE 推流"，不掺编排逻辑。
//
// 推流方案（NestJS 主流 @Sse + RxJS；pi 无服务端推流原语，见 run-event-bus.ts 注释）：
//   POST /dispatch            → 非阻塞创建 run，202 + { planId, runId }
//   GET  /dispatch/:id/events → SSE：先回放历史再接实时流，run_end 后自动关闭
// 前端用法：POST 拿 runId → new EventSource(`/api/v1/dispatch/${runId}/events`) → onmessage 收事件。

import { Body, Controller, Get, HttpCode, HttpStatus, Param, Post, Sse } from '@nestjs/common';
import { map, type Observable } from 'rxjs';

import { MessageEvent } from '@nestjs/common';
import { ZodValidationPipe } from '@/shared';
import { dispatchIntentSchema, type DispatchIntentDto } from '@/api/dto/dispatch.dto';
import { PlannerOrchestrator, type DispatchReceipt } from '@/orchestration/planner-orchestrator';
import { RunEventBus, type RunStreamEvent } from '@/orchestration/run-event-bus';

@Controller('dispatch')
export class DispatchController {
  constructor(
    private readonly orchestrator: PlannerOrchestrator,
    private readonly bus: RunEventBus,
  ) {}

  /** 提交调度意图：创建 Plan + Run 并后台启动 Planner 闭环（进度经 SSE 推送）。 */
  @Post()
  @HttpCode(HttpStatus.ACCEPTED)
  async dispatch(
    @Body(new ZodValidationPipe(dispatchIntentSchema)) body: DispatchIntentDto,
  ): Promise<DispatchReceipt> {
    return this.orchestrator.start(body);
  }

  /** SSE 订阅某个 run 的事件流（run_start → agent/turn/tool 事件 → run_end）。 */
  @Sse(':runId/events')
  streamEvents(@Param('runId') runId: string): Observable<MessageEvent> {
    return this.bus.stream(runId).pipe(map((event: RunStreamEvent) => ({ data: event })));
  }
}
