// Agent 模块 — 内聚 controller + service + repository + dto

import { Module } from '@nestjs/common';
import { AgentController } from './agent.controller';
import { AgentService } from './agent.service';
import { AgentRepository } from './repositories/agent.repo';
import { PythonBackendClient } from '@/clients';

@Module({
  controllers: [AgentController],
  providers: [
    AgentService,
    AgentRepository,
    {
      provide: PythonBackendClient,
      useFactory: () =>
        new PythonBackendClient({
          baseUrl: process.env.PYTHON_BACKEND_URL,
        }),
    },
  ],
  exports: [AgentService, PythonBackendClient],
})
export class AgentModule {}
