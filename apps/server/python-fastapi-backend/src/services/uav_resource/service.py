"""① 无人机资源管理模块"""

from src.domain.enums import UAVStatus
from src.domain.exceptions import InsufficientResourceError
from src.domain.models import UAV, Position, UAVHealthSnapshot
from src.repositories import factory


def get_repository():
    return factory.get_uav_repository()


async def register_uav(uav: UAV) -> UAV:
    return await get_repository().save(uav)


async def get_uav(uav_id: str) -> UAV:
    uav = await get_repository().find_by_id(uav_id)
    if uav is None:
        raise InsufficientResourceError(f"无人机 {uav_id} 不存在")
    return uav


async def list_uavs(status: UAVStatus | None = None) -> list[UAV]:
    if status:
        return await get_repository().find_by_status(status)
    return await get_repository().find_all()


async def update_uav_status(uav_id: str, status: UAVStatus) -> UAV:
    uav = await get_repository().update_status(uav_id, status)
    if uav is None:
        raise InsufficientResourceError(f"无人机 {uav_id} 不存在")
    return uav


async def remove_uav(uav_id: str) -> None:
    if not await get_repository().delete(uav_id):
        raise InsufficientResourceError(f"无人机 {uav_id} 不存在")


async def update_position(uav_id: str, position: Position) -> UAV:
    uav = await get_repository().update_position(uav_id, position.x, position.y, position.z)
    if uav is None:
        raise InsufficientResourceError(f"无人机 {uav_id} 不存在")
    return uav


async def get_snapshot(uav_id: str, timestamp: float = 0.0) -> UAVHealthSnapshot:
    uav = await get_uav(uav_id)
    return UAVHealthSnapshot(
        uav_id=uav.id, position=uav.position,
        battery_remaining=uav.battery, speed=uav.speed,
        heading=0.0, timestamp=timestamp,
    )
