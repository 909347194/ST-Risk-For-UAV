// Python 后端 API 客户端 — 调用算法计算（路径规划、任务分配、风险评估等）

import { createHttpClient } from '../http';
import type { PlanRequest, PlanResponse, AllocateRequest, AllocateResponse } from '@st-risk/shared-ts';

const http = createHttpClient('/api/python');

export const pythonApi = {
  /** 航线规划 */
  planPath(params: PlanRequest) {
    return http.post<PlanResponse>('/paths/plan', params).then(r => r.data);
  },

  /** 任务分配 */
  allocateTasks(params: AllocateRequest) {
    return http.post<AllocateResponse>('/tasks/allocate', params).then(r => r.data);
  },

  /** 风险评估 */
  assessRisk(params: Record<string, unknown>) {
    return http.post('/risk/assess', params).then(r => r.data);
  },

  /** 适配评估 */
  evaluateAdaptability(params: Record<string, unknown>) {
    return http.post('/adaptability/evaluate', params).then(r => r.data);
  },

  /** 列出路径规划算法 */
  listPathAlgorithms() {
    return http.get('/paths/algorithms').then(r => r.data);
  },

  /** 列出任务分配算法 */
  listAllocationAlgorithms() {
    return http.get('/tasks/algorithms').then(r => r.data);
  },
};
