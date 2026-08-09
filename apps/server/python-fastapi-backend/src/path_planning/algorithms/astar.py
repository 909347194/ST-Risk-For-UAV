"""A* 栅格路径搜索算法"""

import heapq
import math

from src.shared.models import Position, Waypoint
from src.path_planning.schemas import Obstacle


def _is_blocked(
    x: float,
    y: float,
    obstacles: list[Obstacle],
) -> bool:
    """检查坐标是否在障碍物内"""
    for obs in obstacles:
        dx = x - obs.center.x
        dy = y - obs.center.y
        if dx * dx + dy * dy <= obs.radius**2:
            return True
    return False


def _heuristic(ax: float, ay: float, gx: float, gy: float) -> float:
    """欧氏距离启发"""
    return math.sqrt((ax - gx) ** 2 + (ay - gy) ** 2)


def astar_plan(
    start: Position,
    goal: Position,
    obstacles: list[Obstacle],
    grid_resolution: float = 1.0,
    bounds: dict | None = None,
    **kwargs,
) -> list[Waypoint]:
    """
    A* 栅格搜索。

    返回航点列表（从 start 到 goal）。
    """
    # 默认搜索范围
    if bounds:
        x_min, x_max = bounds["x_min"], bounds["x_max"]
        y_min, y_max = bounds["y_min"], bounds["y_max"]
    else:
        margin = 50.0
        x_min = min(start.x, goal.x) - margin
        x_max = max(start.x, goal.x) + margin
        y_min = min(start.y, goal.y) - margin
        y_max = max(start.y, goal.y) + margin

    res = grid_resolution
    gx_goal, gy_goal = goal.x, goal.y

    # 起点栅格
    start_node = (round(start.x / res), round(start.y / res))
    goal_node = (round(goal.x / res), round(goal.y / res))

    # 8 方向邻居
    neighbors = [(-1, 0), (1, 0), (0, -1), (0, 1),
                 (-1, -1), (-1, 1), (1, -1), (1, 1)]

    open_set: list[tuple[float, tuple[int, int]]] = []
    heapq.heappush(open_set, (0.0, start_node))

    came_from: dict[tuple[int, int], tuple[int, int]] = {}
    g_score: dict[tuple[int, int], float] = {start_node: 0.0}

    while open_set:
        _, current = heapq.heappop(open_set)

        if current == goal_node:
            # 回溯路径
            path = []
            node = current
            while node in came_from:
                path.append(Waypoint(
                    position=Position(x=node[0] * res, y=node[1] * res),
                    arrival_time=0.0,  # 时间由 service 层计算
                ))
                node = came_from[node]
            path.append(Waypoint(position=Position(x=start.x, y=start.y), arrival_time=0.0))
            path.reverse()
            return path

        cx, cy = current
        for dx, dy in neighbors:
            nx, ny = cx + dx, cy + dy
            wx, wy = nx * res, ny * res

            # 边界检查
            if not (x_min <= wx <= x_max and y_min <= wy <= y_max):
                continue

            # 障碍物检查
            if _is_blocked(wx, wy, obstacles):
                continue

            move_cost = res * (math.sqrt(2) if dx != 0 and dy != 0 else 1.0)
            tentative_g = g_score[current] + move_cost

            neighbor = (nx, ny)
            if tentative_g < g_score.get(neighbor, float("inf")):
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                f = tentative_g + _heuristic(wx, wy, gx_goal, gy_goal)
                heapq.heappush(open_set, (f, neighbor))

    # 无法到达，返回直线
    return [
        Waypoint(position=Position(x=start.x, y=start.y), arrival_time=0.0),
        Waypoint(position=Position(x=goal.x, y=goal.y), arrival_time=0.0),
    ]
