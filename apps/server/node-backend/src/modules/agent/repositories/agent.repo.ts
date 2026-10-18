// Agent 模块 — Repository（Drizzle 持久化，替代原内存 Map）
//
// 约束 4 落地：执行记录不再存内存，落到 Postgres 的 runs 表（payload 列保存原始响应）。
// 真正的调度领域持久化由 services/db/dispatch.repo.ts（Plan/Run/WorkerExecution/Event）承担；
// 此处保持与现有 AgentService 的兼容接口（save/find），但底层已是数据库。

import { Injectable } from '@nestjs/common';
import { eq } from 'drizzle-orm';

import { db } from '@/db';
import { runs } from '@/db/models';
import type { AgentTaskResponse } from '@st-risk/shared-ts';

@Injectable()
export class AgentRepository {
  private runKey(uavId: string, taskId: string): string {
    return `${uavId}:${taskId}`;
  }

  async save(result: AgentTaskResponse): Promise<AgentTaskResponse> {
    const runId = this.runKey(result.uavId, result.taskId);
    await db
      .insert(runs)
      .values({
        id: runId,
        planId: '',
        status: result.status || 'created',
        attempt: 0,
        payload: result,
      })
      .onConflictDoUpdate({
        target: runs.id,
        set: { payload: result, status: result.status || 'created', updatedAt: new Date() },
      });
    return result;
  }

  async find(uavId: string, taskId: string): Promise<AgentTaskResponse | null> {
    const [row] = await db.select().from(runs).where(eq(runs.id, this.runKey(uavId, taskId)));
    return (row?.payload as AgentTaskResponse | undefined) ?? null;
  }
}
