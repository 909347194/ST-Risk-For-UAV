"""④ 任务分配 — 分配编排"""

from src.domain.models import UAV, Task, TaskAllocation
from src.algorithms import get_algorithm, list_algorithms, AlgorithmCategory


def allocate(
    uavs: list[UAV],
    tasks: list[Task],
    algorithm: str = "hungarian",
    params: dict | None = None,
) -> tuple[list[TaskAllocation], list[str]]:
    """执行任务分配，返回 (分配结果, 未分配任务 ID)"""
    algo_fn = get_algorithm(AlgorithmCategory.TASK_ALLOCATION, algorithm)
    return algo_fn(uavs, tasks, **(params or {}))


def list_available_algorithms() -> list[dict]:
    """列出可用的任务分配算法"""
    return list_algorithms(AlgorithmCategory.TASK_ALLOCATION)
