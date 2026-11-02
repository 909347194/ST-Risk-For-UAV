// 应用根模块
// 2026-10-28：旧 AgentModule（agent.controller TODO 占位）已拆除，调度入口唯一 =
// DispatchModule（POST /api/v1/dispatch + SSE 推流）。

import { Module } from '@nestjs/common';
import { CommonModule } from '@/modules';
import { DispatchModule } from '@/api/dispatch.module';

@Module({
  imports: [CommonModule, DispatchModule],
})
export class AppModule {}
