// Python 后端 HTTP 客户端 — 封装对 Python FastAPI 服务的调用

import { Injectable } from '@nestjs/common';

interface HttpClientOptions {
  baseUrl?: string;
  timeout?: number;
}

@Injectable()
export class PythonBackendClient {
  private readonly baseUrl: string;
  private readonly timeout: number;

  constructor(options: HttpClientOptions = {}) {
    this.baseUrl = options.baseUrl || process.env.PYTHON_BACKEND_URL || 'http://localhost:8000';
    this.timeout = options.timeout || 10000;
  }

  /** 通用 GET */
  async get<T>(path: string): Promise<T> {
    const res = await fetch(`${this.baseUrl}${path}`, {
      signal: AbortSignal.timeout(this.timeout),
    });
    if (!res.ok) throw new Error(`Python backend ${res.status}: ${res.statusText}`);
    return res.json() as Promise<T>;
  }

  /** 通用 POST */
  async post<T>(path: string, body: unknown): Promise<T> {
    const res = await fetch(`${this.baseUrl}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(this.timeout),
    });
    if (!res.ok) throw new Error(`Python backend ${res.status}: ${res.statusText}`);
    return res.json() as Promise<T>;
  }

  // ── 业务快捷方法 ──

  /** 航线规划 */
  async planPath(params: Record<string, unknown>) {
    return this.post('/api/v1/paths/plan', params);
  }

  /** 任务分配 */
  async allocateTasks(params: Record<string, unknown>) {
    return this.post('/api/v1/tasks/allocate', params);
  }

  /** 风险评估 */
  async assessRisk(params: Record<string, unknown>) {
    return this.post('/api/v1/risk/assess', params);
  }

  /** 适配评估 */
  async evaluateAdaptability(params: Record<string, unknown>) {
    return this.post('/api/v1/adaptability/evaluate', params);
  }
}
