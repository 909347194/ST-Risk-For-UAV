"""④ 任务分配 — 请求/响应"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from src.domain.models import UAV, Task, TaskAllocation


class AllocateRequest(BaseModel):
    """任务分配请求"""
    uavs: list[UAV] = Field(min_length=1, description="可用无人机列表")
    tasks: list[Task] = Field(min_length=1, description="待分配任务列表")
    algorithm: str = Field(default="hungarian", description="分配算法")
    params: dict | None = Field(default=None, description="算法参数")


class AllocateResponse(BaseModel):
    """任务分配结果"""
    allocations: list[TaskAllocation]
    unassigned_tasks: list[str] = Field(description="未能分配的任务 ID")
    algorithm_used: str


class AllocationRunSummary(BaseModel):
    """一次分配运行的摘要"""
    id: UUID
    algorithm: str
    params: dict | None = None
    uav_count: int
    task_count: int
    assigned_count: int
    unassigned_count: int
    unassigned_task_ids: list[str] = Field(default_factory=list)
    duration_ms: float | None = None
    created_at: datetime


class AllocationRunListResponse(BaseModel):
    runs: list[AllocationRunSummary]
    total: int


class AllocationRunDetailResponse(AllocationRunSummary):
    """明细：含该次运行的 uav→task 配对"""
    allocations: list[TaskAllocation]
