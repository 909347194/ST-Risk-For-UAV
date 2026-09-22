"""容量约束 — 航程 / 载荷可行性检查与构造后修复"""

from __future__ import annotations

import numpy as np

from src.domain.models import UAV, Task
from src.algorithms.task_allocation.energy import greedy_insert_stations, optimal_charging_dp

from .encoding import route_segment_costs


def feasible(
    cost_matrix: np.ndarray,
    n_uav: int,
    n_task: int,
    uavs: list[UAV],
    tasks: list[Task],
    uav_max_ranges: list[float],
    uav_idx: int,
    route_list: list[list[int]],
    *,
    e_matrix=None,
    stations=None,
    station_indices=None,
    sigma: float | None = None,
    energy_strategy: str = "greedy",
    energy_per_meter: float = 0.1,
) -> bool:
    """每机总量容量检查：全部路线总航程 ≤ max_range 且总载荷 ≤ max_payload"""
    total_distance = sum(
        sum(route_segment_costs(cost_matrix, n_uav, n_task, uav_idx, route))
        for route in route_list
    )
    if total_distance > uav_max_ranges[uav_idx]:
        return False
    total_payload = sum(
        tasks[tid].payload_weight for route in route_list for tid in route
    )
    if total_payload > uavs[uav_idx].max_payload:
        return False
    # —— 能量检查（仅 energy 层启用时；构造期快检: 直飞或插站可行即放行）——
    if e_matrix is not None:
        uav = uavs[uav_idx]
        for route in route_list:
            seq = [uav_idx] + [n_uav + tid for tid in route]
            if energy_strategy == "dp":
                plan = optimal_charging_dp(
                    seq, e_matrix, stations, station_indices,
                    uav.battery, sigma, uav.speed, energy_per_meter,
                )
            else:
                plan = greedy_insert_stations(
                    seq, e_matrix, stations, station_indices,
                    uav.battery, sigma, uav.speed, energy_per_meter,
                )
            if plan is None:
                return False
    return True


def rebalance(
    cost_matrix: np.ndarray,
    n_uav: int,
    n_task: int,
    uavs: list[UAV],
    tasks: list[Task],
    uav_max_ranges: list[float],
    routes: dict[int, list[list[int]]],
) -> None:
    """构造后修复：超容 UAV 路线末尾任务移交给最小代价增量且不超容的目标"""
    last_moved_from: dict[int, int] = {}  # task_idx -> 上次移出的 UAV（禁止移回）
    rounds = 0
    while rounds <= n_task:
        rounds += 1
        any_moved = False
        for uav_idx in range(n_uav):
            if feasible(cost_matrix, n_uav, n_task, uavs, tasks, uav_max_ranges, uav_idx, routes[uav_idx]):
                continue
            for route in reversed(routes[uav_idx]):
                task = route[-1]
                best_target: int | None = None
                best_inc = float("inf")
                for target in range(n_uav):
                    if target == uav_idx or last_moved_from.get(task) == target:
                        continue
                    if routes[target]:
                        candidate = routes[target][:-1] + [routes[target][-1] + [task]]
                        prev = routes[target][-1][-1]
                        inc = cost_matrix[n_uav + prev, n_uav + task]
                    else:
                        candidate = [[task]]
                        inc = cost_matrix[target, n_uav + task]
                    if not feasible(cost_matrix, n_uav, n_task, uavs, tasks, uav_max_ranges, target, candidate):
                        continue
                    if inc < best_inc:
                        best_inc = inc
                        best_target = target
                if best_target is not None:
                    route.pop()
                    if not route:
                        routes[uav_idx].remove(route)
                    if routes[best_target]:
                        routes[best_target][-1].append(task)
                    else:
                        routes[best_target].append([task])
                    last_moved_from[task] = uav_idx
                    any_moved = True
                    break
            if any_moved:
                break
        if not any_moved:
            return
