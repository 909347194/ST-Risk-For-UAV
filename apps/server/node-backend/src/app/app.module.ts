// 应用根模块

import { Module } from '@nestjs/common';
import { AgentModule, CommonModule } from '@/modules';

@Module({
  imports: [CommonModule, AgentModule],
})
export class AppModule {}
