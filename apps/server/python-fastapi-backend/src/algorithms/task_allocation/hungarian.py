"""匈牙利算法 — 最优一对一任务分配"""

import itertools

from src.domain.models import UAV, Task, TaskAllocation
from src.utils.utils import distance

PRIORITY_WEIGHT = {"low": 1.0, "medium": 1.5, "high": 2.0, "urgent": 3.0}


def _build_cost_matrix(uavs: list[UAV], tasks: list[Task]) -> list[list[float]]:
    matrix = []
    for uav in uavs:
        row = []
        for task in tasks:
            d = distance(uav.position, task.position)
            w = PRIORITY_WEIGHT.get(task.priority, 1.0)
            row.append(d * w)
        matrix.append(row)
    return matrix


def _hungarian_solve(cost_matrix: list[list[float]]) -> list[tuple[int, int]]:
    """简化版匈牙利算法（穷举，适合小规模）"""
    n_rows = len(cost_matrix)
    n_cols = len(cost_matrix[0])
    n = max(n_rows, n_cols)

    padded = [[0.0] * n for _ in range(n)]
    for i in range(n_rows):
        for j in range(n_cols):
            padded[i][j] = cost_matrix[i][j]

    best_cost = float("inf")
    best_assignment: list[tuple[int, int]] = []

    for perm in itertools.permutations(range(n)):
        cost = sum(padded[i][perm[i]] for i in range(n_rows))
        if cost < best_cost:
            best_cost = cost
            best_assignment = [(i, perm[i]) for i in range(n_rows) if perm[i] < n_cols]

    return best_assignment


def hungarian_allocate(
    uavs: list[UAV], tasks: list[Task], **kwargs
) -> tuple[list[TaskAllocation], list[str]]:
    """使用匈牙利算法进行任务分配"""
    if not uavs or not tasks:
        return [], [t.id for t in tasks]

    cost_matrix = _build_cost_matrix(uavs, tasks)
    assignment = _hungarian_solve(cost_matrix)

    allocations = []
    assigned_task_indices = set()
    for uav_idx, task_idx in assignment:
        cost = cost_matrix[uav_idx][task_idx]
        allocations.append(
            TaskAllocation(
                uav_id=uavs[uav_idx].id,
                task_id=tasks[task_idx].id,
                estimated_cost=cost,
            )
        )
        assigned_task_indices.add(task_idx)

    unassigned = [tasks[i].id for i in range(len(tasks)) if i not in assigned_task_indices]
    return allocations, unassigned
