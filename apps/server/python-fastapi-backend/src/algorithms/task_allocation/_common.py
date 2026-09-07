"""任务分配算法公共模块 — 常量与代价/航程工具（DE / CW 共用）"""

import numpy as np

from src.domain.models import UAV, Task
from src.utils.utils import distance

PRIORITY_WEIGHT = {"low": 1.0, "medium": 1.5, "high": 2.0, "urgent": 3.0}


def build_cost_matrix(uavs: list[UAV], tasks: list[Task]) -> np.ndarray:
    """(N_uav+N_task)×(N_uav+N_task) 代价矩阵 — 距离 × 任务优先级权重，对角 0

    索引约定: 行/列 0..N_uav-1 为 UAV，N_uav..N_uav+N_task-1 为任务。
    """
    points = [u.position for u in uavs] + [t.position for t in tasks]
    n = len(points)
    matrix = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            d = distance(points[i], points[j])
            if j >= len(uavs):
                task = tasks[j - len(uavs)]
                d *= PRIORITY_WEIGHT.get(task.priority.value, 1.0)
            matrix[i, j] = d
    return matrix


def derive_uav_ranges(
    uavs: list[UAV],
    uav_max_ranges: list[float] | None = None,
    energy_per_meter: float = 0.1,
) -> list[float]:
    """推导每机最大航程：显式参数优先（校验长度与正值），缺省按电池/能耗率推算"""
    if uav_max_ranges is not None:
        if len(uav_max_ranges) != len(uavs):
            raise ValueError(
                f"uav_max_ranges 长度必须等于 UAV 数 ({len(uavs)})，当前: {len(uav_max_ranges)}"
            )
        if any(r <= 0 for r in uav_max_ranges):
            raise ValueError(f"uav_max_ranges 各项必须 > 0，当前: {uav_max_ranges}")
        return list(uav_max_ranges)
    return [
        u.battery / energy_per_meter if energy_per_meter > 0 else float("inf")
        for u in uavs
    ]
