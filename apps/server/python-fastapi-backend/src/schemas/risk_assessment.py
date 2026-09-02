"""③ 飞行风险评估 — 请求/响应"""

from pydantic import BaseModel, Field

from src.models.models import UAV, Task, Obstacle, RiskAssessment


class RiskAssessRequest(BaseModel):
    """风险评估请求"""
    uav: UAV
    task: Task
    obstacles: list[Obstacle] = Field(default_factory=list)
    weather_factor: float = Field(default=0.0, ge=0, le=1, description="气象因子 (0=晴好, 1=恶劣)")


class RiskAssessResponse(BaseModel):
    """风险评估结果"""
    assessment: RiskAssessment
    pass_check: bool = Field(description="是否通过风险检查（低于阈值）")
