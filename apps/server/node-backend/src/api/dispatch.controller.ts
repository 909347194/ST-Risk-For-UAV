// 调度 API — 对外 HTTP 入口（替代旧 modules/agent/agent.controller.ts 的 execute 占位）。
// 本控制器只做"收单 → 交给 PlannerOrchestrator"，不掺编排逻辑。

import { Body, Controller, Post } from '@nestjs/common';

import { ZodValidationPipe } from '@/shared';
import { dispatchIntentSchema, type DispatchIntentDto } from '@/api/dto/dispatch.dto';
import type { PlannerOrchestrator, DispatchOutcome } from '@/orchestration/planner-orchestrator';

@Controller('dispatch')
export class DispatchController {
  constructor(private readonly orchestrator: PlannerOrchestrator) {}

  /** 提交调度意图，创建 Plan + Run 并启动 Planner 闭环。 */
  @Post()
  async dispatch(
    @Body(new ZodValidationPipe(dispatchIntentSchema)) body: DispatchIntentDto,
  ): Promise<DispatchOutcome> {
    return this.orchestrator.execute(body);
  }
}
