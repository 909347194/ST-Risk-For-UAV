"""① 无人机资源管理模块"""

from src.models.models import UAV, UAVHealthSnapshot, Position
from src.models.enums import UAVStatus
from src.models.exceptions import InsufficientResourceError
from src.repositories.uav_repo import UAVRepository

_repo = UAVRepository()


def get_repository() -> UAVRepository:
    return _repo


def register_uav(uav: UAV) -> UAV:
    return _repo.save(uav)


def get_uav(uav_id: str) -> UAV:
    uav = _repo.find_by_id(uav_id)
    if uav is None:
        raise InsufficientResourceError(f"无人机 {uav_id} 不存在")
    return uav


def list_uavs(status: UAVStatus | None = None) -> list[UAV]:
    if status:
        return _repo.find_by_status(status)
    return _repo.find_all()


def update_uav_status(uav_id: str, status: UAVStatus) -> UAV:
    uav = _repo.update_status(uav_id, status)
    if uav is None:
        raise InsufficientResourceError(f"无人机 {uav_id} 不存在")
    return uav


def remove_uav(uav_id: str) -> None:
    if not _repo.delete(uav_id):
        raise InsufficientResourceError(f"无人机 {uav_id} 不存在")


def update_position(uav_id: str, position: Position) -> UAV:
    uav = _repo.update_position(uav_id, position.x, position.y, position.z)
    if uav is None:
        raise InsufficientResourceError(f"无人机 {uav_id} 不存在")
    return uav


def get_snapshot(uav_id: str, timestamp: float = 0.0) -> UAVHealthSnapshot:
    uav = get_uav(uav_id)
    return UAVHealthSnapshot(
        uav_id=uav.id, position=uav.position,
        battery_remaining=uav.battery, speed=uav.speed,
        heading=0.0, timestamp=timestamp,
    )
