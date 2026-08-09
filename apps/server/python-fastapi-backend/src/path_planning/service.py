"""路径规划业务编排"""

from src.shared.models import Position, PathPlan
from src.path_planning.schemas import Obstacle
from src.path_planning.algorithms import REGISTRY


def plan_path(
    uav_id: str,
    task_id: str,
    start: Position,
    goal: Position,
    obstacles: list[Obstacle],
    speed: float = 10.0,
    algorithm: str = "astar",
    params: dict | None = None,
    **kwargs,
) -> PathPlan:
    """执行路径规划"""
    if algorithm not in REGISTRY:
        raise ValueError(f"未知算法: {algorithm}，可用: {list(REGISTRY.keys())}")

    algo_fn = REGISTRY[algorithm]
    waypoints = algo_fn(
        start=start,
        goal=goal,
        obstacles=obstacles,
        **(params or {}),
        **kwargs,
    )

    # 计算总距离和时间
    total_distance = 0.0
    for i in range(1, len(waypoints)):
        dx = waypoints[i].position.x - waypoints[i - 1].position.x
        dy = waypoints[i].position.y - waypoints[i - 1].position.y
        dz = waypoints[i].position.z - waypoints[i - 1].position.z
        total_distance += (dx**2 + dy**2 + dz**2) ** 0.5

    estimated_time = total_distance / speed if speed > 0 else 0.0

    return PathPlan(
        uav_id=uav_id,
        task_id=task_id,
        waypoints=waypoints,
        total_distance=total_distance,
        estimated_time=estimated_time,
    )


def list_algorithms() -> list[dict]:
    """列出所有可用算法"""
    from src.path_planning.algorithms import ALGORITHM_INFO
    return ALGORITHM_INFO
