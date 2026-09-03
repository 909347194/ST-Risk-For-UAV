// Agent Service — 编排业务逻辑，调用 Python 后端

import { Injectable } from '@nestjs/common';
import { PythonBackendClient } from '@/clients';
import type { AgentTaskResponse } from '@st-risk/shared-ts';
import { AgentRepository } from './repositories/agent.repo';

@Injectable()
export class AgentService {
  constructor(
    private readonly pythonClient: PythonBackendClient,
    private readonly repo: AgentRepository,
  ) {}

  async executeTask(uavId: string, taskId: string, instruction: string): Promise<AgentTaskResponse> {
    // TODO: Agent 编排逻辑
    // 1. 调用 Python 端适配评估
    // 2. 调用 Python 端风险评估
    // 3. 调用 Python 端航线规划
    // 4. 汇总结果
    const result: AgentTaskResponse = { uavId, taskId, instruction, status: 'pending' };
    return this.repo.save(result);
  }
}
