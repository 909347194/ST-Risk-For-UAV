"""⑥ 飞行监控模块"""

from src.domain.models import UAVHealthSnapshot
from src.repositories.flight_log_repo import FlightLogRepository

_repo = FlightLogRepository()


def get_repository() -> FlightLogRepository:
    return _repo


def record_snapshot(snapshot: UAVHealthSnapshot) -> UAVHealthSnapshot:
    _repo.append_snapshot(snapshot)
    anomalies = detect_anomalies(snapshot)
    if anomalies:
        snapshot.is_anomaly = True
        snapshot.anomaly_reasons = anomalies
        for a in anomalies:
            _repo.append_alert(snapshot.uav_id, a)
    return snapshot


def detect_anomalies(snapshot: UAVHealthSnapshot) -> list[str]:
    anomalies: list[str] = []
    if snapshot.battery_remaining < 10.0:
        anomalies.append(f"电量过低: {snapshot.battery_remaining:.1f}Wh")
    if snapshot.speed > 30.0:
        anomalies.append(f"速度异常: {snapshot.speed:.1f}m/s")
    if snapshot.position.z < 0:
        anomalies.append(f"高度异常: {snapshot.position.z:.1f}m（低于地面）")
    if snapshot.position.z > 120:
        anomalies.append(f"高度异常: {snapshot.position.z:.1f}m（超出限高）")
    return anomalies


def get_track(uav_id: str, limit: int = 100) -> list[UAVHealthSnapshot]:
    return _repo.get_track(uav_id, limit)


def get_alerts(uav_id: str) -> list[str]:
    return _repo.get_alerts(uav_id)


def clear_alerts(uav_id: str) -> None:
    _repo.clear_alerts(uav_id)


def get_active_count() -> int:
    return len(_repo.get_active_uav_ids())
