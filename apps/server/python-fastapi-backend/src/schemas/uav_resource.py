"""① 无人机资源管理 — 请求/响应"""

from pydantic import BaseModel, Field

from src.models.models import UAV, UAVHealthSnapshot


class UAVCreateRequest(BaseModel):
    """注册无人机请求"""
    id: str
    x: float
    y: float
    z: float = 0.0
    speed: float = Field(gt=0, description="最大速度 (m/s)")
    max_payload: float = Field(ge=0, description="最大载荷 (kg)")
    battery: float = Field(gt=0, description="电池容量 (Wh)")


class UAVStatusUpdateRequest(BaseModel):
    """更新状态请求"""
    status: str = Field(description="目标状态: idle|assigned|in_flight|returning|maintenance|offline")


class UAVResponse(BaseModel):
    """无人机信息"""
    uav: UAV


class UAVListResponse(BaseModel):
    """无人机列表"""
    uavs: list[UAV]
    total: int


class UAVSnapshotResponse(BaseModel):
    """健康快照"""
    snapshot: UAVHealthSnapshot
