// 调度领域持久化 — Drizzle Repository（替代原内存 Map）
// 负责 Plan / Run / WorkerExecution / DispatchEvent 的落库与查询，提供可追溯的真实状态。

import { Injectable } from '@nestjs/common';
import { eq } from 'drizzle-orm';

import { db } from '@/db';
import {
  dispatchEvents,
  plans,
  runs,
  workerExecutions,
  type NewDispatchEvent,
  type NewPlan,
  type NewRun,
  type NewWorkerExecution,
  type PlanRow,
  type RunRow,
  type WorkerExecutionRow,
} from '@/db/models';

@Injectable()
export class DispatchRepository {
  // ── Plan ──
  async createPlan(input: NewPlan): Promise<PlanRow> {
    const [row] = await db.insert(plans).values(input).returning();
    return row;
  }

  async getPlan(id: string): Promise<PlanRow | undefined> {
    const [row] = await db.select().from(plans).where(eq(plans.id, id));
    return row;
  }

  // ── Run ──
  async createRun(input: NewRun): Promise<RunRow> {
    const [row] = await db.insert(runs).values(input).returning();
    return row;
  }

  async getRun(id: string): Promise<RunRow | undefined> {
    const [row] = await db.select().from(runs).where(eq(runs.id, id));
    return row;
  }

  async updateRunStatus(id: string, status: string, finished = false): Promise<void> {
    await db
      .update(runs)
      .set({
        status,
        updatedAt: new Date(),
        finishedAt: finished ? new Date() : undefined,
      })
      .where(eq(runs.id, id));
  }

  // ── WorkerExecution ──
  async recordWorkerExecution(input: NewWorkerExecution): Promise<WorkerExecutionRow> {
    const [row] = await db.insert(workerExecutions).values(input).returning();
    return row;
  }

  async listWorkerExecutions(runId: string): Promise<WorkerExecutionRow[]> {
    return db.select().from(workerExecutions).where(eq(workerExecutions.runId, runId));
  }

  // ── DispatchEvent ──
  async appendEvent(input: NewDispatchEvent): Promise<void> {
    await db.insert(dispatchEvents).values(input);
  }
}
