"""⑤ 航线规划 — 请求/响应"""

from pydantic import BaseModel, Field

from src.domain.models import Position, Obstacle, PathPlan


class PlanRequest(BaseModel):
    """航线规划请求"""
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
    """航线规划结果"""
    plan: PathPlan
    algorithm_used: str
