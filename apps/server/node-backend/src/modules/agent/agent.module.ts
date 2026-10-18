// Agent 模块 — 内聚 controller + service + repository + dto

import { Module } from '@nestjs/common';
import { AgentController } from './agent.controller';
import { AgentService } from './agent.service';
import { AgentRepository } from './repositories/agent.repo';
import { AlgorithmClient } from '@/services/python/python-client';

@Module({
  controllers: [AgentController],
  providers: [
    AgentService,
    AgentRepository,
    {
      provide: AlgorithmClient,
      useFactory: () =>
        new AlgorithmClient({
          baseUrl: process.env.PYTHON_BACKEND_URL,
        }),
    },
  ],
  exports: [AgentService, AlgorithmClient],
})
export class AgentModule {}
