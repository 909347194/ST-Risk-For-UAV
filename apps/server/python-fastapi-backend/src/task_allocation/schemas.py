"""任务分配请求/响应模型"""

from pydantic import BaseModel, Field

from src.shared.models import UAV, Task, TaskAllocation


class AllocateRequest(BaseModel):
    """任务分配请求"""
    uavs: list[UAV] = Field(min_length=1, description="可用无人机列表")
    tasks: list[Task] = Field(min_length=1, description="待分配任务列表")
    algorithm: str = Field(default="hungarian", description="分配算法")
    params: dict | None = Field(default=None, description="算法参数")


class AllocateResponse(BaseModel):
    """任务分配响应"""
    allocations: list[TaskAllocation]
    unassigned_tasks: list[str] = Field(description="未能分配的任务 ID")
    algorithm_used: str


class AlgorithmInfo(BaseModel):
    """算法信息"""
    name: str
    description: str
    params_schema: dict | None = None
