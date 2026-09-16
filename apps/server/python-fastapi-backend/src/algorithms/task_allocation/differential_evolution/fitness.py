"""适应度评估 — 路径代价与航程 / deadline / 负载均衡约束"""

from __future__ import annotations

import numpy as np

from src.domain.models import UAV, Task

from .config import RANGE_PENALTY, DEADLINE_VIOLATION_PENALTY, LOAD_BALANCE_WEIGHT
from .encoding import decode, compute_path_costs


def evaluate(
    cost_matrix: np.ndarray,
    n_uav: int,
    n_task: int,
    uav_max_ranges: list[float],
    individual: list[int],
) -> float:
    """基础适应度 = 总路径代价 + 超航程固定惩罚"""
    uav_task_dict = decode(cost_matrix, n_uav, n_task, individual)
    costs_dict = compute_path_costs(cost_matrix, n_uav, n_task, uav_task_dict)
    total_cost = 0.0
    for uav_id, seq in uav_task_dict.items():
        if not seq:
            continue
        seg_cost = sum(costs_dict[uav_id])
        if seg_cost > uav_max_ranges[uav_id]:
            total_cost += seg_cost + RANGE_PENALTY  # 超航程惩罚
        else:
            total_cost += seg_cost
    return total_cost


def evaluate_constrained(
    cost_matrix: np.ndarray,
    n_uav: int,
    n_task: int,
    uavs: list[UAV],
    tasks: list[Task],
    uav_max_ranges: list[float],
    individual: list[int],
    alpha: float = 1.0,
    beta: float = 0.5,
    gamma: float = 1.0,
    penalty_weight: float = 500.0,
) -> float:
    """约束感知适应度 (Zhao et al. 2012, Eq. 23)

    fitness = alpha·Σ(path_cost) + beta·max_flight_time
              + gamma·penalty_weight·Σ(constraint_violations)

    约束:
      1. 最大航程约束
      2. 任务 deadline 约束 (Task.time_limit)
      3. 负载均衡约束
    """
    uav_task_dict = decode(cost_matrix, n_uav, n_task, individual)
    costs_dict = compute_path_costs(cost_matrix, n_uav, n_task, uav_task_dict)
    total_path_cost = 0.0
    max_flight_time = 0.0
    violations = 0.0

    for uav_id, seq in uav_task_dict.items():
        if not seq:
            continue
        path_cost = sum(costs_dict[uav_id])
        total_path_cost += path_cost

        speed = uavs[uav_id].speed
        flight_time = path_cost / speed if speed > 0 else 0.0
        max_flight_time = max(max_flight_time, flight_time)

        # 约束 1: 最大航程
        max_range = uav_max_ranges[uav_id]
        if path_cost > max_range:
            violations += (path_cost - max_range) / max_range

    # 约束 2: 任务 deadline（累计到达时刻）
    for uav_id, seq in uav_task_dict.items():
        speed = uavs[uav_id].speed
        cumulative = 0.0
        for k, tid in enumerate(seq):
            if speed > 0:
                cumulative += costs_dict[uav_id][k] / speed
            task = tasks[tid]
            if task.time_limit is not None and cumulative > task.time_limit:
                violations += DEADLINE_VIOLATION_PENALTY

    # 约束 3: 负载均衡
    task_counts = [len(seq) for seq in uav_task_dict.values()]
    if task_counts:
        violations += float(np.var(task_counts)) * LOAD_BALANCE_WEIGHT

    fitness = (
        alpha * total_path_cost
        + beta * max_flight_time
        + gamma * penalty_weight * violations
    )
    return fitness
