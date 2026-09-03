"""⑥ 飞行监控 API"""

from fastapi import APIRouter

from src.domain.models import UAVHealthSnapshot, Position
from src.schemas.flight_monitoring import (
    SnapshotSubmitRequest,
    SnapshotSubmitResponse,
    TrackResponse,
    AlertListResponse,
    MonitoringOverview,
)
from src.services import flight_monitoring as service

router = APIRouter()


@router.post("/snapshot", response_model=SnapshotSubmitResponse)
async def submit_snapshot(req: SnapshotSubmitRequest) -> SnapshotSubmitResponse:
    """提交无人机健康快照"""
    snapshot = UAVHealthSnapshot(
        uav_id=req.uav_id,
        position=Position(x=req.x, y=req.y, z=req.z),
        battery_remaining=req.battery_remaining,
        speed=req.speed,
        heading=req.heading,
        timestamp=req.timestamp,
    )
    result = service.record_snapshot(snapshot)
    return SnapshotSubmitResponse(
        snapshot=result,
        has_anomaly=result.is_anomaly,
        alerts=service.get_alerts(req.uav_id),
    )


@router.get("/track/{uav_id}", response_model=TrackResponse)
async def get_track(uav_id: str, limit: int = 100) -> TrackResponse:
    """获取飞行轨迹"""
    snapshots = service.get_track(uav_id, limit)
    return TrackResponse(uav_id=uav_id, snapshots=snapshots, total=len(snapshots))


@router.get("/alerts/{uav_id}", response_model=AlertListResponse)
async def get_alerts(uav_id: str) -> AlertListResponse:
    """获取告警"""
    return AlertListResponse(uav_id=uav_id, alerts=service.get_alerts(uav_id))


@router.delete("/alerts/{uav_id}", status_code=204)
async def clear_alerts(uav_id: str) -> None:
    """清除告警"""
    service.clear_alerts(uav_id)


@router.get("/overview", response_model=MonitoringOverview)
async def get_overview() -> MonitoringOverview:
    """监控总览"""
    return MonitoringOverview(active_uavs=service.get_active_count())
