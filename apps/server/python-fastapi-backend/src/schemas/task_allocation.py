"""④ 任务分配 — 请求/响应"""

from pydantic import BaseModel, Field

from src.domain.models import UAV, Task, TaskAllocation, ChargingStation


class AllocateRequest(BaseModel):
    """任务分配请求"""
    uavs: list[UAV] = Field(min_length=1, description="可用无人机列表")
    tasks: list[Task] = Field(min_length=1, description="待分配任务列表")
    algorithm: str = Field(default="hungarian", description="分配算法")
    params: dict | None = Field(default=None, description="算法参数")
    stations: list[ChargingStation] = Field(default_factory=list, description="充电站列表(仅 cw/de 使用)")
    sigma: float | None = Field(default=None, gt=0, description="安全余量 (Wh),缺省 0.1×电池")
    energy_strategy: str = Field(default="auto", description="充电策略 greedy|dp|none|auto")


class ChargeEventOut(BaseModel):
    """一次充电事件"""
    station_id: str
    charge_wh: float = Field(ge=0, description="充电量 (Wh)")
    arrive_time: float = Field(ge=0, description="到站时刻 (s)")
    leave_time: float = Field(ge=0, description="离站时刻 (s)")


class UAVRechargePlanOut(BaseModel):
    """一条路线的补给计划"""
    uav_id: str
    feasible: bool
    total_time: float = Field(ge=0, description="飞行 + 充电总时间 (s)")
    total_energy: float = Field(ge=0, description="总飞行能耗 (Wh)")
    charges: list[ChargeEventOut] = Field(default_factory=list)


class AllocateResponse(BaseModel):
    """任务分配结果"""
    allocations: list[TaskAllocation]
    unassigned_tasks: list[str] = Field(description="未能分配的任务 ID")
    algorithm_used: str
    recharge_plans: list[UAVRechargePlanOut] = Field(default_factory=list, description="补给计划(每条路线一条)")
