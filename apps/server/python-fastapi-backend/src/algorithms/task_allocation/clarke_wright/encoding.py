"""路线编码 — 逐段代价与 DE 整数个体转换（与 DE 编码约定一致）"""

from __future__ import annotations

import numpy as np


def route_segment_costs(
    cost_matrix: np.ndarray,
    n_uav: int,
    n_task: int,
    uav_idx: int,
    route: list[int],
) -> list[float]:
    """路线逐段代价，首段从该 UAV 位置出发"""
    current = uav_idx
    seg: list[float] = []
    for tid in route:
        seg.append(float(cost_matrix[current, n_uav + tid]))
        current = n_uav + tid
    return seg


def to_individual(
    cost_matrix: np.ndarray,
    n_uav: int,
    n_task: int,
    routes: dict[int, list[list[int]]],
) -> list[int]:
    """路线 → DE 整数编码: gene[tid] = 该任务所属 UAV 下标"""
    individual = [0] * n_task
    for uav_idx, route_list in routes.items():
        for route in route_list:
            for tid in route:
                individual[tid] = uav_idx
    return individual
