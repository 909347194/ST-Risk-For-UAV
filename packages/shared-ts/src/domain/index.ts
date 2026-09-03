// 共享领域模型 — 前端 + Node 后端通用
// 与 Python 端 domain/models.py 对齐

import { UAVStatus, TaskPriority, RiskLevel } from '../enums';

export interface Position {
  x: number;
  y: number;
  z: number;
}

export interface UAV {
  id: string;
  position: Position;
  speed: number;
  maxPayload: number;
  battery: number;
  status: UAVStatus;
}

export interface Task {
  id: string;
  position: Position;
  priority: TaskPriority;
  payloadWeight: number;
  timeLimit?: number;
}

export interface Waypoint {
  position: Position;
  arrivalTime: number;
}

export interface PathPlan {
  uavId: string;
  taskId: string;
  waypoints: Waypoint[];
  totalDistance: number;
  estimatedTime: number;
}

export interface TaskAllocation {
  uavId: string;
  taskId: string;
  estimatedCost: number;
}

export interface Obstacle {
  center: Position;
  radius: number;
}

export interface RiskAssessment {
  uavId: string;
  taskId: string;
  riskLevel: RiskLevel;
  collisionRisk: number;
  weatherRisk: number;
  batteryRisk: number;
  overallScore: number;
  details: string[];
}

export interface AdaptabilityResult {
  uavId: string;
  taskId: string;
  capable: boolean;
  payloadOk: boolean;
  batteryOk: boolean;
  rangeOk: boolean;
  timeOk: boolean;
  score: number;
  reasons: string[];
}

export interface UAVHealthSnapshot {
  uavId: string;
  position: Position;
  batteryRemaining: number;
  speed: number;
  heading: number;
  timestamp: number;
  isAnomaly: boolean;
  anomalyReasons: string[];
}
