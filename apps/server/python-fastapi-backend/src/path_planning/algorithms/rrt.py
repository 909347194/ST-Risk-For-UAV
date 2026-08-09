"""RRT (快速随机树) 路径规划算法"""

import math
import random

from src.shared.models import Position, Waypoint
from src.path_planning.schemas import Obstacle


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


def _is_blocked(
    point: tuple[float, float],
    obstacles: list[Obstacle],
) -> bool:
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
    """从 from_pt 向 to_pt 方向走 step_size"""
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
    """
    RRT 快速随机树算法。

    通过随机采样逐步扩展搜索树，适合复杂障碍物环境。
    """
    if bounds:
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

    # 树结构: 节点 -> 父节点
    tree: dict[tuple[float, float], tuple[float, float] | None] = {start_pt: None}

    for _ in range(max_iterations):
        # 90% 随机采样，10% 直接朝目标
        if random.random() < 0.1:
            sample = goal_pt
        else:
            sample = (
                random.uniform(x_min, x_max),
                random.uniform(y_min, y_max),
            )

        # 找树中最近节点
        nearest = min(tree.keys(), key=lambda p: _distance(p, sample))

        # 向采样点走一步
        new_point = _steer(nearest, sample, step_size)

        # 碰撞检查
        if _is_blocked(new_point, obstacles):
            continue

        # 检查路径上是否有障碍（简化：只检查中点）
        mid = ((nearest[0] + new_point[0]) / 2, (nearest[1] + new_point[1]) / 2)
        if _is_blocked(mid, obstacles):
            continue

        # 加入树
        tree[new_point] = nearest

        # 到达目标附近
        if _distance(new_point, goal_pt) <= goal_threshold:
            # 回溯路径
            path_coords = [goal_pt, new_point]
            node = new_point
            while tree[node] is not None:
                path_coords.append(tree[node])
                node = tree[node]  # type: ignore
            path_coords.reverse()

            return [
                Waypoint(
                    position=Position(x=p[0], y=p[1]),
                    arrival_time=0.0,
                )
                for p in path_coords
            ]

    # 未找到路径，返回直线
    return [
        Waypoint(position=Position(x=start.x, y=start.y), arrival_time=0.0),
        Waypoint(position=Position(x=goal.x, y=goal.y), arrival_time=0.0),
    ]
