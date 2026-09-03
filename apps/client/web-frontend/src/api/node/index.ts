// Node 后端 API 客户端 — 调用 Agent 业务逻辑

import { createHttpClient } from '../http';
import type { AgentTaskRequest, AgentTaskResponse, CreateUavRequest, UavResponse } from '@st-risk/shared-ts';

const http = createHttpClient('/api/v1');

export const nodeApi = {
  /** 执行 Agent 任务 */
  executeAgentTask(params: AgentTaskRequest) {
    return http.post<AgentTaskResponse>('/agent/execute', params).then(r => r.data);
  },

  /** 注册无人机 */
  createUav(params: CreateUavRequest) {
    return http.post<UavResponse>('/uavs', params).then(r => r.data);
  },

  /** 列出无人机 */
  listUavs(status?: string) {
    return http.get('/uavs', { params: { status } }).then(r => r.data);
  },

  /** 查询无人机 */
  getUav(id: string) {
    return http.get(`/uavs/${id}`).then(r => r.data);
  },

  /** 健康检查 */
  health() {
    return http.get('/health').then(r => r.data);
  },
};
