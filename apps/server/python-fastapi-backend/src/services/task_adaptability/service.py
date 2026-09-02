"""② 无人机任务适配评估模块"""

from src.models.models import UAV, Task, AdaptabilityResult
from src.utils.utils import distance


def evaluate(uav: UAV, task: Task, min_battery_reserve: float = 0.2) -> AdaptabilityResult:
    reasons: list[str] = []
    scores: list[float] = []

    payload_ok = uav.max_payload >= task.payload_weight
    if payload_ok:
        scores.append(1.0 - task.payload_weight / uav.max_payload if uav.max_payload > 0 else 1.0)
    else:
        reasons.append(f"载荷不足: 需要 {task.payload_weight}kg, 最大 {uav.max_payload}kg")
        scores.append(0.0)

    dist = distance(uav.position, task.position)
    est_consumption = dist * 2 * 0.1
    battery_ok = uav.battery * (1 - min_battery_reserve) >= est_consumption
    if battery_ok:
        scores.append((uav.battery - est_consumption) / uav.battery if uav.battery > 0 else 0.0)
    else:
        reasons.append(f"电量不足: 预估消耗 {est_consumption:.1f}Wh")
        scores.append(0.0)

    range_ok = dist <= uav.speed * 60
    if not range_ok:
        reasons.append(f"距离过远: {dist:.1f}m 超出单次航程")
    scores.append(1.0 if range_ok else 0.0)

    time_ok = True
    if task.time_limit is not None:
        flight_time = dist / uav.speed if uav.speed > 0 else float("inf")
        time_ok = flight_time <= task.time_limit
        if not time_ok:
            reasons.append(f"时间不足: 预估 {flight_time:.1f}s, 限制 {task.time_limit}s")
    scores.append(1.0 if time_ok else 0.0)

    capable = payload_ok and battery_ok and range_ok and time_ok
    return AdaptabilityResult(
        uav_id=uav.id, task_id=task.id, capable=capable,
        payload_ok=payload_ok, battery_ok=battery_ok,
        range_ok=range_ok, time_ok=time_ok,
        score=round(sum(scores) / len(scores), 4) if scores else 0.0,
        reasons=reasons,
    )


def evaluate_all(uavs: list[UAV], task: Task, min_battery_reserve: float = 0.2) -> list[AdaptabilityResult]:
    results = [evaluate(u, task, min_battery_reserve) for u in uavs]
    results.sort(key=lambda r: r.score, reverse=True)
    return results
