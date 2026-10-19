// AlgorithmClient — Python 算法服务的唯一通信闸门（见 agent-architecture-node-landing.md §7.9）
//
// 铁律：Planner 工具 / Worker 都不直接 fetch Python，全部经本类。它统一负责：
//   ① HTTP/JSON 协议  ② 超时（per-method）  ③ AbortSignal 贯通（pi execute 的 signal → fetch）
//   ④ 错误映射（→ code/retryable，供 WorkerResult.error 使用）  ⑤ 边界校验（防 schema 漂移）
// 由 clients/python-backend 迁移而来（原弱类型 + 统一 10s 超时的两个问题在此修正）。

import { z } from 'zod';

// ── 错误契约 ──
// 400/422 → retryable:false（参数错，调用方应换参数/换路）
// 5xx / 网络 / 超时 → retryable:true（瞬时故障，可重试）
export class AlgorithmError extends Error {
  constructor(
    message: string,
    readonly code: string,
    readonly retryable: boolean,
    readonly status?: number,
  ) {
    super(message);
    this.name = 'AlgorithmError';
  }
}

// ── 请求/响应类型（真相源 = Python pydantic，见 docs/architecture/python-api-contract.md；字段名与之逐字一致）──
export interface PositionPayload {
  x: number;
  y: number;
  z?: number;
}
/** Python `UAV`（domain/models.py）的 wire 形状。 */
export interface UavPayload {
  id: string;
  position: PositionPayload;
  speed: number;
  max_payload: number;
  battery: number;
  status?: string;
}
/** Python `Task` 的 wire 形状。 */
export interface TaskPayload {
  id: string;
  position: PositionPayload;
  priority?: string;
  payload_weight: number;
  time_limit?: number | null;
}
/** Python `TaskAllocation` 的 wire 形状。 */
export interface TaskAllocationPayload {
  uav_id: string;
  task_id: string;
  estimated_cost: number;
}
export interface AllocateTasksRequest {
  /** 可用无人机完整对象（≥1）；字段对齐 Python `AllocateRequest.uavs: list[UAV]`。 */
  uavs: UavPayload[];
  /** 待分配任务完整对象（≥1）；字段对齐 `AllocateRequest.tasks: list[Task]`。 */
  tasks: TaskPayload[];
  algorithm?: string;
  params?: Record<string, unknown>;
}
export interface AllocateTasksResponse {
  allocations: TaskAllocationPayload[];
  /** 未能分配的任务 ID（无可行方案 = 全部；领域事实，不是错误）。 */
  unassigned_tasks: string[];
  /** 实际使用的算法（必须回带，可追溯）。 */
  algorithm_used: string;
}
export interface PlanPathRequest {
  uavId: string;
  origin: unknown;
  destination: unknown;
  constraints?: Record<string, unknown>;
  algorithm?: string;
}
export interface PlanPathResponse {
  path: unknown;
  algorithm_used: string;
}
export interface AssessRiskRequest {
  uavId?: string;
  region?: unknown;
  snapshot?: unknown;
}
export interface AssessRiskResponse {
  risk: unknown;
}
export interface AdaptabilityRequest {
  uavId: string;
  taskId: string;
}
export interface AdaptabilityResponse {
  adaptable: boolean;
  score?: number;
  reasons?: unknown[];
}

export interface CallOptions {
  /** 上游取消信号（pi AgentTool.execute 的 signal 一路传进来）。 */
  signal?: AbortSignal;
  /** 覆盖本次调用超时（重算法配大值，别用统一 10s 误杀）。 */
  timeoutMs?: number;
  /** X-Correlation-Id（= pi toolCallId）：Python 侧透传进日志，全链路回放。 */
  correlationId?: string;
}

export interface AlgorithmClientOptions {
  baseUrl?: string;
  /** 默认超时。 */
  defaultTimeoutMs?: number;
  /** per-method 超时（如 { '/api/v1/tasks/allocate': 30_000 }）。 */
  timeouts?: Record<string, number>;
}

/** 响应边界 schema（zod）—— 与 Python pydantic 对齐（真相源见 python-api-contract.md）。 */
const allocateTasksResponseSchema = z.object({
  allocations: z.array(
    z.object({
      uav_id: z.string(),
      task_id: z.string(),
      estimated_cost: z.number(),
    }),
  ),
  unassigned_tasks: z.array(z.string()),
  algorithm_used: z.string(),
});

export class AlgorithmClient {
  private readonly baseUrl: string;
  private readonly defaultTimeoutMs: number;
  private readonly timeouts: Record<string, number>;

  constructor(options: AlgorithmClientOptions = {}) {
    this.baseUrl = options.baseUrl || process.env.PYTHON_BACKEND_URL || 'http://localhost:8000';
    this.defaultTimeoutMs = options.defaultTimeoutMs ?? 10_000;
    this.timeouts = options.timeouts ?? {};
  }

  // ── 业务方法（类型化；新增算法 = 加一个方法 + contracts schema，5 步见 §7.9）──

  /** 任务分配（Hungarian/Auction）。 */
  async allocateTasks(req: AllocateTasksRequest, opts: CallOptions = {}): Promise<AllocateTasksResponse> {
    return this.post('/api/v1/tasks/allocate', req, allocateTasksResponseSchema, opts);
  }

  /** 航线规划（A-star / RRT）。 */
  async planPath(req: PlanPathRequest, opts: CallOptions = {}): Promise<PlanPathResponse> {
    // TODO：补 zod 响应 schema（以 PlanResponse pydantic 为准）
    return this.post('/api/v1/paths/plan', req, z.any(), opts);
  }

  /** 风险评估。 */
  async assessRisk(req: AssessRiskRequest, opts: CallOptions = {}): Promise<AssessRiskResponse> {
    return this.post('/api/v1/risk/assess', req, z.any(), opts);
  }

  /** 适配评估。 */
  async evaluateAdaptability(req: AdaptabilityRequest, opts: CallOptions = {}): Promise<AdaptabilityResponse> {
    return this.post('/api/v1/adaptability/evaluate', req, z.any(), opts);
  }

  /** 健康检查（编排前探活可选）。 */
  async health(opts: CallOptions = {}): Promise<{ status: string }> {
    return this.get('/api/v1/health', opts);
  }

  // ── 传输层 ──

  private async get<T>(path: string, opts: CallOptions): Promise<T> {
    return this.request<T>(path, { method: 'GET' }, opts);
  }

  private async post<T>(
    path: string,
    body: unknown,
    schema: z.ZodType<T>,
    opts: CallOptions,
  ): Promise<T> {
    const raw = await this.request<unknown>(
      path,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      },
      opts,
    );
    const parsed = schema.safeParse(raw);
    if (!parsed.success) {
      // schema 漂移：宁可炸在边界，不把脏数据传给 Worker/Planner
      throw new AlgorithmError(`response schema mismatch: ${parsed.error.message}`, 'CONTRACT_MISMATCH', false);
    }
    return parsed.data;
  }

  private async request<T>(path: string, init: RequestInit, opts: CallOptions): Promise<T> {
    const timeoutMs = opts.timeoutMs ?? this.timeouts[path] ?? this.defaultTimeoutMs;
    const signal = mergeSignals(opts.signal, AbortSignal.timeout(timeoutMs));
    const headers = new Headers(init.headers);
    if (opts.correlationId) headers.set('X-Correlation-Id', opts.correlationId);

    let res: Response;
    try {
      res = await fetch(`${this.baseUrl}${path}`, { ...init, headers, signal });
    } catch (error) {
      if (opts.signal?.aborted) {
        throw new AlgorithmError('request aborted by caller', 'ABORTED', false);
      }
      const e = error as { name?: string; message?: string };
      if (e.name === 'TimeoutError') {
        throw new AlgorithmError(`timeout after ${timeoutMs}ms: ${path}`, 'TIMEOUT', true);
      }
      throw new AlgorithmError(e.message ?? 'network error', 'NETWORK', true);
    }

    if (!res.ok) {
      const retryable = res.status >= 500;
      throw new AlgorithmError(
        `Python backend ${res.status} ${res.statusText}: ${path}`,
        `HTTP_${res.status}`,
        retryable,
        res.status,
      );
    }
    return (await res.json()) as T;
  }
}

/** 合并调用方取消信号与超时信号（AbortSignal.any 在 Node ≥20.3 可用，兜底手写）。 */
function mergeSignals(a?: AbortSignal, b?: AbortSignal): AbortSignal | undefined {
  if (!a) return b;
  if (!b) return a;
  const anyFn = (AbortSignal as unknown as { any?: (s: AbortSignal[]) => AbortSignal }).any;
  if (anyFn) return anyFn([a, b]);
  const controller = new AbortController();
  a.addEventListener('abort', () => controller.abort(a.reason), { once: true });
  b.addEventListener('abort', () => controller.abort(b.reason), { once: true });
  return controller.signal;
}
