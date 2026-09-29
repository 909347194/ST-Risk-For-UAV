"""RRT (快速随机树) 路径规划算法"""

import math
import random

from src.algorithms.path_planning._common import validate_bounds
from src.domain.models import Position, Waypoint, Obstacle


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


def _is_blocked(point: tuple[float, float], obstacles: list[Obstacle]) -> bool:
    for obs in obstacles:
        dx = point[0] - obs.center.x
        dy = point[1] - obs.center.y
        if dx * dx + dy * dy <= obs.radius**2:
            return True
    return False


def _steer(
    from_pt: tuple[float, float],
    to_pt: tuple[float, float],
    step_size: float,
) -> tuple[float, float]:
    d = _distance(from_pt, to_pt)
    if d <= step_size:
        return to_pt
    ratio = step_size / d
    return (
        from_pt[0] + (to_pt[0] - from_pt[0]) * ratio,
        from_pt[1] + (to_pt[1] - from_pt[1]) * ratio,
    )


def rrt_plan(
    start: Position,
    goal: Position,
    obstacles: list[Obstacle],
    step_size: float = 2.0,
    max_iterations: int = 5000,
    goal_threshold: float = 2.0,
    bounds: dict | None = None,
    **kwargs,
) -> list[Waypoint]:
    """RRT 快速随机树算法，返回航点列表"""
    if bounds:
        validate_bounds(bounds)
        x_min, x_max = bounds["x_min"], bounds["x_max"]
        y_min, y_max = bounds["y_min"], bounds["y_max"]
    else:
        margin = 50.0
        x_min = min(start.x, goal.x) - margin
        x_max = max(start.x, goal.x) + margin
        y_min = min(start.y, goal.y) - margin
        y_max = max(start.y, goal.y) + margin

    start_pt = (start.x, start.y)
    goal_pt = (goal.x, goal.y)

    tree: dict[tuple[float, float], tuple[float, float] | None] = {start_pt: None}

    for _ in range(max_iterations):
        sample = goal_pt if random.random() < 0.1 else (
            random.uniform(x_min, x_max),
            random.uniform(y_min, y_max),
        )

        nearest = min(tree.keys(), key=lambda p: _distance(p, sample))
        new_point = _steer(nearest, sample, step_size)

        if _is_blocked(new_point, obstacles):
            continue

        mid = ((nearest[0] + new_point[0]) / 2, (nearest[1] + new_point[1]) / 2)
        if _is_blocked(mid, obstacles):
            continue

        tree[new_point] = nearest

        if _distance(new_point, goal_pt) <= goal_threshold:
            path_coords = [goal_pt, new_point]
            node = new_point
            while tree[node] is not None:
                path_coords.append(tree[node])
                node = tree[node]  # type: ignore
            path_coords.reverse()
            return [
                Waypoint(position=Position(x=p[0], y=p[1]), arrival_time=0.0)
                for p in path_coords
            ]

    return [
        Waypoint(position=Position(x=start.x, y=start.y), arrival_time=0.0),
        Waypoint(position=Position(x=goal.x, y=goal.y), arrival_time=0.0),
    ]
