// 共享 API 类型 — 请求/响应，与 Python 端 schemas 对齐

import { UAV, Task, PathPlan, TaskAllocation, RiskAssessment, AdaptabilityResult, UAVHealthSnapshot } from '../domain';

// ── ① 无人机资源管理 ──

export interface CreateUavRequest {
  id: string;
  x: number;
  y: number;
  z?: number;
  speed: number;
  maxPayload: number;
  battery: number;
}

export interface UavResponse {
  uav: UAV;
}

export interface UavListResponse {
  uavs: UAV[];
  total: number;
}

// ── ④ 任务分配 ──

export interface AllocateRequest {
  uavs: UAV[];
  tasks: Task[];
  algorithm?: string;
  params?: Record<string, unknown>;
}

export interface AllocateResponse {
  allocations: TaskAllocation[];
  unassignedTasks: string[];
  algorithmUsed: string;
}

// ── ⑤ 航线规划 ──

export interface PlanRequest {
  uavId: string;
  taskId: string;
  start: { x: number; y: number; z?: number };
  goal: { x: number; y: number; z?: number };
  obstacles?: { center: { x: number; y: number; z?: number }; radius: number }[];
  speed?: number;
  algorithm?: string;
  params?: Record<string, unknown>;
}

export interface PlanResponse {
  plan: PathPlan;
  algorithmUsed: string;
}

// ── ③ 风险评估 ──

export interface RiskAssessRequest {
  uav: UAV;
  task: Task;
  obstacles?: { center: { x: number; y: number; z?: number }; radius: number }[];
  weatherFactor?: number;
}

export interface RiskAssessResponse {
  assessment: RiskAssessment;
  passCheck: boolean;
}

// ── ② 适配评估 ──

export interface AdaptabilityRequest {
  uavId: string;
  task: Task;
  minBatteryReserve?: number;
}

export interface AdaptabilityResponse {
  result: AdaptabilityResult;
}

// ── ⑥ 飞行监控 ──

export interface SnapshotSubmitRequest {
  uavId: string;
  x: number;
  y: number;
  z?: number;
  batteryRemaining: number;
  speed: number;
  heading: number;
  timestamp: number;
}

export interface SnapshotSubmitResponse {
  snapshot: UAVHealthSnapshot;
  hasAnomaly: boolean;
  alerts: string[];
}

export interface TrackResponse {
  uavId: string;
  snapshots: UAVHealthSnapshot[];
  total: number;
}

// ── Agent ──

export interface AgentTaskRequest {
  uavId: string;
  taskId: string;
  instruction: string;
  params?: Record<string, unknown>;
}

export interface AgentTaskResponse {
  uavId: string;
  taskId: string;
  instruction: string;
  status: string;
}
