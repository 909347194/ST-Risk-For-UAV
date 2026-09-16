"""整数编码 ↔ 分配方案 — 基因型与表现型的双向转换

个体编码约定: [UAV_ID_task0, UAV_ID_task1, ..., UAV_ID_taskN-1]
  长度 = 任务数，第 i 个基因的值 = 执行任务 i 的 UAV 编号，值域 [0, N_uav)。
"""

from __future__ import annotations

import numpy as np


def encode_assignment(uav_task_dict: dict[int, list[int]], n_task: int) -> list[int]:
    """分配方案 → 整数个体（与 decode 互逆）

    输入: {uav_id: [task_id, ...]}（如 ClarkeWright 的 routes / 任意可行分配）
    输出: [UAV_ID_task0, UAV_ID_task1, ..., UAV_ID_taskN-1]

    要求覆盖全部任务 — 缺失任务属于输入错误，提前以清晰错误拒绝。
    """
    covered = [False] * n_task
    individual = [0] * n_task
    for uav_id, task_list in uav_task_dict.items():
        for task_id in task_list:
            if not 0 <= task_id < n_task:
                raise ValueError(f"encode 输入中任务编号越界: {task_id}（任务数 {n_task}）")
            covered[task_id] = True
            individual[task_id] = int(uav_id)
    missing = [i for i, ok in enumerate(covered) if not ok]
    if missing:
        raise ValueError(f"encode 输入未覆盖全部任务，缺失任务: {missing}")
    return individual


def nearest_neighbor_seq(
    cost_matrix: np.ndarray,
    n_uav: int,
    n_task: int,
    uav_id: int,
    task_list: list[int],
) -> tuple[list[int], list[float]]:
    """从 UAV 位置出发按最近邻贪心排定任务顺序

    返回 (顺序, 逐段代价) — decode 与 compute_path_costs 共享的行走逻辑。
    """
    if not task_list:
        return [], []
    current_idx = uav_id  # 从 UAV 位置出发
    seq: list[int] = []
    seg: list[float] = []
    remaining = task_list.copy()
    while remaining:
        nearest = min(
            remaining,
            key=lambda tid: cost_matrix[current_idx, n_uav + tid],
        )
        seq.append(nearest)
        seg.append(float(cost_matrix[current_idx, n_uav + nearest]))
        remaining.remove(nearest)
        current_idx = n_uav + nearest
    return seq, seg


def decode(
    cost_matrix: np.ndarray,
    n_uav: int,
    n_task: int,
    individual: list[int] | np.ndarray,
) -> dict[int, list[int]]:
    """整数编码 → {uav_id: [task_id, ...]} (最近邻排序)

    个体: [UAV_ID_task0, UAV_ID_task1, ..., UAV_ID_taskN-1]
    """
    uav_tasks: dict[int, list[int]] = {i: [] for i in range(n_uav)}
    for task_id, uav_id in enumerate(individual):
        uav_tasks[int(uav_id)].append(task_id)

    sorted_tasks: dict[int, list[int]] = {}
    for uav_id, task_list in uav_tasks.items():
        seq, _ = nearest_neighbor_seq(cost_matrix, n_uav, n_task, uav_id, task_list)
        sorted_tasks[uav_id] = seq
    return sorted_tasks


def compute_path_costs(
    cost_matrix: np.ndarray,
    n_uav: int,
    n_task: int,
    uav_task_dict: dict[int, list[int]],
) -> dict[int, list[float]]:
    """计算每架 UAV 任务序列的逐段代价"""
    costs: dict[int, list[float]] = {}
    for uav_id, task_list in uav_task_dict.items():
        _, seg = nearest_neighbor_seq(cost_matrix, n_uav, n_task, uav_id, task_list)
        costs[uav_id] = seg
    return costs
