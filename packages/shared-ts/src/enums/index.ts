// 共享枚举 — 前端 + Node 后端通用

export enum UAVStatus {
  IDLE = 'idle',
  ASSIGNED = 'assigned',
  IN_FLIGHT = 'in_flight',
  RETURNING = 'returning',
  MAINTENANCE = 'maintenance',
  OFFLINE = 'offline',
}

export enum TaskPriority {
  LOW = 'low',
  MEDIUM = 'medium',
  HIGH = 'high',
  URGENT = 'urgent',
}

export enum RiskLevel {
  LOW = 'low',
  MEDIUM = 'medium',
  HIGH = 'high',
  CRITICAL = 'critical',
}
