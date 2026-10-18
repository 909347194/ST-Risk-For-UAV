// 应用根模块

import { Module } from '@nestjs/common';
import { AgentModule, CommonModule } from '@/modules';
import { DispatchModule } from '@/api/dispatch.module';

@Module({
  imports: [CommonModule, AgentModule, DispatchModule],
})
export class AppModule {}
