// 调度模块装配 — Registry 静态注册 + Router + Orchestrator + 算法闸门 + 持久化。
// V1 静态注册（启动装配），不做远程注册中心；新增能力 = definitions 文件 + 一行 register。

import { Module } from '@nestjs/common';

import { DispatchController } from '@/api/dispatch.controller';
import { WorkerRegistry } from '@/registry/worker-registry';
import { allocationWorkerDefinition } from '@/registry/definitions/allocation.def';
import { WorkerRouter } from '@/orchestration/worker-router';
import { PlannerOrchestrator } from '@/orchestration/planner-orchestrator';
import { AlgorithmClient } from '@/services/python/python-client';
import { DispatchRepository } from '@/services/db/dispatch.repo';

@Module({
  controllers: [DispatchController],
  providers: [
    {
      provide: AlgorithmClient,
      useFactory: () =>
        new AlgorithmClient({
          baseUrl: process.env.PYTHON_BACKEND_URL,
          // per-method 超时：分配算法可能远慢于健康检查，别用统一 10s 误杀
          timeouts: { '/api/v1/tasks/allocate': 30_000, '/api/v1/paths/plan': 30_000 },
        }),
    },
    {
      provide: WorkerRegistry,
      useFactory: (python: AlgorithmClient) => {
        const registry = new WorkerRegistry();
        registry.register(allocationWorkerDefinition(python));
        // TODO Phase 2：注册 risk / route / resource / validation 能力
        return registry;
      },
      inject: [AlgorithmClient],
    },
    {
      provide: WorkerRouter,
      useFactory: (registry: WorkerRegistry) => new WorkerRouter(registry),
      inject: [WorkerRegistry],
    },
    DispatchRepository,
    PlannerOrchestrator,
  ],
  exports: [WorkerRegistry, WorkerRouter, AlgorithmClient],
})
export class DispatchModule {}
