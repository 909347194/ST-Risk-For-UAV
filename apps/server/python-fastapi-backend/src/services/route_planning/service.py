"""⑤ 航线规划 — 路径计算"""

from src.models.models import Position, PathPlan, Obstacle
from src.algorithms import get_algorithm, list_algorithms, AlgorithmCategory
from src.utils.utils import distance


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
    """执行路径规划，返回完整路径方案"""
    algo_fn = get_algorithm(AlgorithmCategory.PATH_PLANNING, algorithm)

    waypoints = algo_fn(
        start=start,
        goal=goal,
        obstacles=obstacles,
        **(params or {}),
        **kwargs,
    )

    total_distance = 0.0
    for i in range(1, len(waypoints)):
        total_distance += distance(waypoints[i - 1].position, waypoints[i].position)

    estimated_time = total_distance / speed if speed > 0 else 0.0

    return PathPlan(
        uav_id=uav_id,
        task_id=task_id,
        waypoints=waypoints,
        total_distance=total_distance,
        estimated_time=estimated_time,
    )


def list_available_algorithms() -> list[dict]:
    """列出可用的路径规划算法"""
    return list_algorithms(AlgorithmCategory.PATH_PLANNING)
