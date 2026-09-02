"""② 任务适配评估 — 请求/响应"""

from pydantic import BaseModel, Field

from src.models.models import UAV, Task, AdaptabilityResult


class AdaptabilityRequest(BaseModel):
    """适配评估请求"""
    uav_id: str = Field(description="无人机 ID（单机评估）")
    task: Task
    min_battery_reserve: float = Field(default=0.2, ge=0, le=1, description="最低电量保留比例")


class BatchAdaptabilityRequest(BaseModel):
    """批量评估请求"""
    uavs: list[UAV] = Field(min_length=1)
    task: Task
    min_battery_reserve: float = Field(default=0.2, ge=0, le=1)


class AdaptabilityResponse(BaseModel):
    """适配评估结果"""
    result: AdaptabilityResult


class BatchAdaptabilityResponse(BaseModel):
    """批量评估结果"""
    results: list[AdaptabilityResult]
    best_uav_id: str | None = Field(description="最优无人机 ID")
