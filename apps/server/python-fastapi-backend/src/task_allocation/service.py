"""任务分配业务编排"""

from src.shared.models import UAV, Task, TaskAllocation
from src.task_allocation.algorithms import REGISTRY


def allocate(
    uavs: list[UAV],
    tasks: list[Task],
    algorithm: str = "hungarian",
    params: dict | None = None,
) -> tuple[list[TaskAllocation], list[str]]:
    """
    执行任务分配。

    返回: (分配结果列表, 未分配的任务 ID 列表)
    """
    if algorithm not in REGISTRY:
        raise ValueError(f"未知算法: {algorithm}，可用: {list(REGISTRY.keys())}")

    algo_fn = REGISTRY[algorithm]
    allocations, unassigned = algo_fn(uavs, tasks, **(params or {}))

    return allocations, unassigned


def list_algorithms() -> list[dict]:
    """列出所有可用算法"""
    from src.task_allocation.algorithms import ALGORITHM_INFO
    return ALGORITHM_INFO
