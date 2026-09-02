"""① 无人机资源管理 API"""

from fastapi import APIRouter, HTTPException

from src.models.models import UAV, Position
from src.models.enums import UAVStatus
from src.models.exceptions import InsufficientResourceError
from src.schemas.uav_resource import (
    UAVCreateRequest,
    UAVStatusUpdateRequest,
    UAVResponse,
    UAVListResponse,
    UAVSnapshotResponse,
)
from src.services import uav_resource as service

router = APIRouter()


@router.post("", response_model=UAVResponse)
async def register_uav(req: UAVCreateRequest) -> UAVResponse:
    """注册一架无人机"""
    uav = UAV(
        id=req.id,
        position=Position(x=req.x, y=req.y, z=req.z),
        speed=req.speed,
        max_payload=req.max_payload,
        battery=req.battery,
    )
    return UAVResponse(uav=service.register_uav(uav))


@router.get("", response_model=UAVListResponse)
async def list_uavs(status: str | None = None) -> UAVListResponse:
    """列出无人机"""
    uav_status = UAVStatus(status) if status else None
    uavs = service.list_uavs(uav_status)
    return UAVListResponse(uavs=uavs, total=len(uavs))


@router.get("/{uav_id}", response_model=UAVResponse)
async def get_uav(uav_id: str) -> UAVResponse:
    """查询单架无人机"""
    try:
        return UAVResponse(uav=service.get_uav(uav_id))
    except InsufficientResourceError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/{uav_id}/status", response_model=UAVResponse)
async def update_status(uav_id: str, req: UAVStatusUpdateRequest) -> UAVResponse:
    """更新无人机状态"""
    try:
        status = UAVStatus(req.status)
        return UAVResponse(uav=service.update_uav_status(uav_id, status))
    except (InsufficientResourceError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{uav_id}", status_code=204)
async def remove_uav(uav_id: str) -> None:
    """移除无人机"""
    try:
        service.remove_uav(uav_id)
    except InsufficientResourceError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{uav_id}/snapshot", response_model=UAVSnapshotResponse)
async def get_snapshot(uav_id: str) -> UAVSnapshotResponse:
    """获取健康快照"""
    try:
        return UAVSnapshotResponse(snapshot=service.get_snapshot(uav_id))
    except InsufficientResourceError as e:
        raise HTTPException(status_code=404, detail=str(e))
