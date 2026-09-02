"""③ 飞行风险评估模块"""

from src.models.models import UAV, Task, Obstacle, PathPlan, RiskAssessment
from src.models.enums import RiskLevel
from src.utils.utils import distance, clamp


def _collision(uav: UAV, obstacles: list[Obstacle]) -> float:
    if not obstacles:
        return 0.0
    min_dist = min(distance(uav.position, o.center) - o.radius for o in obstacles)
    if min_dist <= 0:
        return 1.0
    return clamp(1.0 - min_dist / 10.0, 0.0, 1.0)


def _weather(factor: float) -> float:
    return clamp(factor, 0.0, 1.0)


def _battery(uav: UAV, task: Task) -> float:
    if uav.battery <= 0:
        return 1.0
    return clamp(distance(uav.position, task.position) * 2 * 0.1 / uav.battery, 0.0, 1.0)


def _level(score: float) -> RiskLevel:
    if score < 0.25:
        return RiskLevel.LOW
    elif score < 0.5:
        return RiskLevel.MEDIUM
    elif score < 0.75:
        return RiskLevel.HIGH
    return RiskLevel.CRITICAL


def assess(
    uav: UAV, task: Task, obstacles: list[Obstacle] | None = None,
    path: PathPlan | None = None, weather_factor: float = 0.0,
) -> RiskAssessment:
    obstacles = obstacles or []
    details: list[str] = []

    c = _collision(uav, obstacles)
    w = _weather(weather_factor)
    b = _battery(uav, task)

    if c > 0.5:
        details.append(f"碰撞风险较高: {c:.2f}")
    if w > 0.5:
        details.append(f"气象条件恶劣: {w:.2f}")
    if b > 0.5:
        details.append(f"电量消耗风险高: {b:.2f}")

    overall = c * 0.4 + w * 0.3 + b * 0.3
    return RiskAssessment(
        uav_id=uav.id, task_id=task.id, risk_level=_level(overall),
        collision_risk=round(c, 4), weather_risk=round(w, 4),
        battery_risk=round(b, 4), overall_score=round(overall, 4),
        details=details,
    )
