"""① 无人机资源仓储"""

from src.models.models import UAV
from src.models.enums import UAVStatus
from src.repositories.base import InMemoryRepository


class UAVRepository(InMemoryRepository[UAV, str]):
    """无人机仓储"""

    def _extract_id(self, entity: UAV) -> str:
        return entity.id

    def find_by_status(self, status: UAVStatus) -> list[UAV]:
        """按状态筛选"""
        return [u for u in self._store.values() if u.status == status]

    def update_status(self, uav_id: str, status: UAVStatus) -> UAV | None:
        """更新状态"""
        uav = self.find_by_id(uav_id)
        if uav:
            uav.status = status
            self._store[uav_id] = uav
        return uav

    def update_position(self, uav_id: str, x: float, y: float, z: float) -> UAV | None:
        """更新位置"""
        uav = self.find_by_id(uav_id)
        if uav:
            uav.position.x = x
            uav.position.y = y
            uav.position.z = z
            self._store[uav_id] = uav
        return uav
