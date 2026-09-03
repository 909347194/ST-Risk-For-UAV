"""⑥ 飞行监控 — 请求/响应"""

from pydantic import BaseModel, Field

from src.domain.models import UAVHealthSnapshot


class SnapshotSubmitRequest(BaseModel):
    """提交健康快照"""
    uav_id: str
    x: float
    y: float
    z: float = 0.0
    battery_remaining: float = Field(ge=0, description="剩余电量 (Wh)")
    speed: float = Field(ge=0, description="当前速度 (m/s)")
    heading: float = Field(ge=0, lt=360, description="航向角 (°)")
    timestamp: float = Field(ge=0, description="时间戳 (s)")


class SnapshotSubmitResponse(BaseModel):
    """提交结果"""
    snapshot: UAVHealthSnapshot
    has_anomaly: bool
    alerts: list[str]


class TrackResponse(BaseModel):
    """飞行轨迹"""
    uav_id: str
    snapshots: list[UAVHealthSnapshot]
    total: int


class AlertListResponse(BaseModel):
    """告警列表"""
    uav_id: str
    alerts: list[str]


class MonitoringOverview(BaseModel):
    """监控总览"""
    active_uavs: int
