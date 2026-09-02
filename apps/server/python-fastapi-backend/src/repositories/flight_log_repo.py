"""⑥ 飞行监控仓储 — 轨迹日志 + 告警记录"""

from src.models.models import UAVHealthSnapshot
from src.repositories.base import InMemoryRepository


class FlightLogRepository:
    """
    飞行日志仓储。

    轨迹和告警按 uav_id 分桶存储，支持追加、查询、清除。
    """

    def __init__(self) -> None:
        self._tracks: dict[str, list[UAVHealthSnapshot]] = {}
        self._alerts: dict[str, list[str]] = {}

    # ── 轨迹 ──

    def append_snapshot(self, snapshot: UAVHealthSnapshot) -> None:
        self._tracks.setdefault(snapshot.uav_id, []).append(snapshot)

    def get_track(self, uav_id: str, limit: int = 100) -> list[UAVHealthSnapshot]:
        track = self._tracks.get(uav_id, [])
        return track[-limit:]

    def get_latest(self, uav_id: str) -> UAVHealthSnapshot | None:
        track = self._tracks.get(uav_id)
        return track[-1] if track else None

    def get_active_uav_ids(self) -> list[str]:
        return list(self._tracks.keys())

    # ── 告警 ──

    def append_alert(self, uav_id: str, alert: str) -> None:
        self._alerts.setdefault(uav_id, []).append(alert)

    def get_alerts(self, uav_id: str) -> list[str]:
        return self._alerts.get(uav_id, [])

    def clear_alerts(self, uav_id: str) -> None:
        self._alerts.pop(uav_id, None)

    # ── 管理 ──

    def clear(self) -> None:
        self._tracks.clear()
        self._alerts.clear()
