"""路径规划请求/响应模型"""

from pydantic import BaseModel, Field

from src.shared.models import Position, PathPlan


class Obstacle(BaseModel):
    """障碍物（圆形）"""
    center: Position
    radius: float = Field(gt=0, description="半径 (m)")


class PlanRequest(BaseModel):
    """路径规划请求"""
    uav_id: str
    task_id: str
    start: Position
    goal: Position
    obstacles: list[Obstacle] = Field(default_factory=list, description="障碍物列表")
    speed: float = Field(default=10.0, gt=0, description="UAV 速度 (m/s)")
    algorithm: str = Field(default="astar", description="规划算法")
    params: dict | None = Field(default=None, description="算法参数")
    grid_resolution: float = Field(default=1.0, gt=0, description="栅格分辨率 (m)")
    bounds: dict | None = Field(
        default=None,
        description="规划区域边界 {x_min, x_max, y_min, y_max}",
    )


class PlanResponse(BaseModel):
    """路径规划响应"""
    plan: PathPlan
    algorithm_used: str


class AlgorithmInfo(BaseModel):
    """算法信息"""
    name: str
    description: str
    params_schema: dict | None = None
