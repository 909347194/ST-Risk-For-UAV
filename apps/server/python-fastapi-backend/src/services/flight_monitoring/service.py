"""⑥ 飞行监控模块"""

from src.domain.models import UAVHealthSnapshot
from src.repositories import factory


def get_repository():
    return factory.get_flight_log_repository()


async def record_snapshot(snapshot: UAVHealthSnapshot) -> UAVHealthSnapshot:
    anomalies = detect_anomalies(snapshot)
    if anomalies:
        snapshot.is_anomaly = True
        snapshot.anomaly_reasons = anomalies
    await get_repository().append_snapshot(snapshot)
    for a in anomalies:
        await get_repository().append_alert(snapshot.uav_id, a)
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


async def get_track(uav_id: str, limit: int = 100) -> list[UAVHealthSnapshot]:
    return await get_repository().get_track(uav_id, limit)


async def get_alerts(uav_id: str) -> list[str]:
    return await get_repository().get_alerts(uav_id)


async def clear_alerts(uav_id: str) -> None:
    await get_repository().clear_alerts(uav_id)


async def get_active_count() -> int:
    return len(await get_repository().get_active_uav_ids())
