"""核心领域模型 — 零业务逻辑，纯数据定义"""

from pydantic import BaseModel, Field

from src.models.enums import UAVStatus, TaskPriority, RiskLevel


# ── 基础 ──────────────────────────────────────────────

class Position(BaseModel):
    """三维坐标"""
    x: float
    y: float
    z: float = 0.0


# ── 无人机 ────────────────────────────────────────────

class UAV(BaseModel):
    """无人机"""
    id: str
    position: Position
    speed: float = Field(gt=0, description="最大速度 (m/s)")
    max_payload: float = Field(ge=0, description="最大载荷 (kg)")
    battery: float = Field(gt=0, description="电池容量 (Wh)")
    status: UAVStatus = UAVStatus.IDLE


class UAVHealthSnapshot(BaseModel):
    """无人机健康快照（飞行监控用）"""
    uav_id: str
    position: Position
    battery_remaining: float = Field(ge=0, description="剩余电量 (Wh)")
    speed: float = Field(ge=0, description="当前速度 (m/s)")
    heading: float = Field(ge=0, lt=360, description="航向角 (°)")
    timestamp: float = Field(ge=0, description="时间戳 (s)")
    is_anomaly: bool = False
    anomaly_reasons: list[str] = Field(default_factory=list)


# ── 任务 ──────────────────────────────────────────────

class Task(BaseModel):
    """任务"""
    id: str
    position: Position
    priority: TaskPriority = TaskPriority.MEDIUM
    payload_weight: float = Field(ge=0, description="所需载荷 (kg)")
    time_limit: float | None = Field(default=None, gt=0, description="时间限制 (s)")


class TaskAllocation(BaseModel):
    """任务分配结果"""
    uav_id: str
    task_id: str
    estimated_cost: float = Field(ge=0, description="预估代价")


# ── 路径 ──────────────────────────────────────────────

class Waypoint(BaseModel):
    """航点"""
    position: Position
    arrival_time: float = Field(ge=0, description="预计到达时间 (s)")


class PathPlan(BaseModel):
    """路径规划结果"""
    uav_id: str
    task_id: str
    waypoints: list[Waypoint]
    total_distance: float = Field(ge=0, description="总距离 (m)")
    estimated_time: float = Field(ge=0, description="预计耗时 (s)")


class Obstacle(BaseModel):
    """障碍物（圆形）"""
    center: Position
    radius: float = Field(gt=0, description="半径 (m)")


# ── 评估 ──────────────────────────────────────────────

class RiskAssessment(BaseModel):
    """飞行风险评估结果"""
    uav_id: str
    task_id: str
    risk_level: RiskLevel
    collision_risk: float = Field(ge=0, le=1, description="碰撞风险 [0,1]")
    weather_risk: float = Field(ge=0, le=1, description="气象风险 [0,1]")
    battery_risk: float = Field(ge=0, le=1, description="电量风险 [0,1]")
    overall_score: float = Field(ge=0, le=1, description="综合风险分 [0,1]")
    details: list[str] = Field(default_factory=list)


class AdaptabilityResult(BaseModel):
    """任务适配评估结果"""
    uav_id: str
    task_id: str
    capable: bool
    payload_ok: bool
    battery_ok: bool
    range_ok: bool
    time_ok: bool
    score: float = Field(ge=0, le=1, description="适配分 [0,1]")
    reasons: list[str] = Field(default_factory=list)
