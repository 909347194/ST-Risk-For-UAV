"""共享领域模型"""

from enum import Enum

from pydantic import BaseModel, Field


class Position(BaseModel):
    """三维坐标"""
    x: float
    y: float
    z: float = 0.0


class UAVStatus(str, Enum):
    IDLE = "idle"
    ASSIGNED = "assigned"
    IN_FLIGHT = "in_flight"
    RETURNING = "returning"


class UAV(BaseModel):
    """无人机"""
    id: str
    position: Position
    speed: float = Field(gt=0, description="最大速度 (m/s)")
    max_payload: float = Field(ge=0, description="最大载荷 (kg)")
    battery: float = Field(gt=0, description="电池容量 (Wh)")
    status: UAVStatus = UAVStatus.IDLE


class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class Task(BaseModel):
    """任务"""
    id: str
    position: Position
    priority: TaskPriority = TaskPriority.MEDIUM
    payload_weight: float = Field(ge=0, description="所需载荷 (kg)")
    time_limit: float | None = Field(default=None, gt=0, description="时间限制 (s)")


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


class TaskAllocation(BaseModel):
    """任务分配结果"""
    uav_id: str
    task_id: str
    estimated_cost: float = Field(ge=0, description="预估代价")
