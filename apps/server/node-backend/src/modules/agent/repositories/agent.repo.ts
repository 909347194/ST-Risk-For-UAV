// Agent 模块 — Repository

import { Injectable } from '@nestjs/common';
import type { AgentTaskResponse } from '@st-risk/shared-ts';

@Injectable()
export class AgentRepository {
  private readonly tasks = new Map<string, AgentTaskResponse>();

  async save(result: AgentTaskResponse): Promise<AgentTaskResponse> {
    this.tasks.set(`${result.uavId}:${result.taskId}`, result);
    return result;
  }

  async find(uavId: string, taskId: string): Promise<AgentTaskResponse | null> {
    return this.tasks.get(`${uavId}:${taskId}`) ?? null;
  }
}
