"""④ 任务分配 — 分配编排"""

from src.domain.models import UAV, Task, TaskAllocation
from src.algorithms import get_algorithm, list_algorithms, AlgorithmCategory
from src.algorithms.task_allocation.energy import RechargePlan


def _resolve_strategy(algorithm: str, strategy: str) -> str:
    """energy_strategy 解析: auto → 算法默认;非法值抛 ValueError"""
    if strategy == "auto":
        strategy = {"cw": "greedy", "de": "dp"}.get(algorithm, "none")
    if strategy not in ("greedy", "dp", "none"):
        raise ValueError(f"energy_strategy 必须为 greedy|dp|none|auto，当前: {strategy}")
    return strategy


def _run(
    uavs: list[UAV],
    tasks: list[Task],
    algorithm: str,
    params: dict | None,
    stations: list | None,
    sigma: float | None,
    energy_strategy: str,
) -> tuple[list[TaskAllocation], list[str], list[RechargePlan]]:
    """执行任务分配,返回 (分配结果, 未分配任务 ID, 补给计划)

    stations / sigma / energy_strategy 透传给所有算法;
    hungarian/auction 通过 **kwargs 吸收忽略。
    """
    algo_fn = get_algorithm(AlgorithmCategory.TASK_ALLOCATION, algorithm)
    kwargs = dict(params or {})
    kwargs["stations"] = stations or []
    kwargs["sigma"] = sigma
    kwargs["energy_strategy"] = _resolve_strategy(algorithm, energy_strategy)
    result = algo_fn(uavs, tasks, **kwargs)
    if len(result) == 3:
        return result
    return result[0], result[1], []


def allocate(
    uavs: list[UAV],
    tasks: list[Task],
    algorithm: str = "hungarian",
    params: dict | None = None,
) -> tuple[list[TaskAllocation], list[str]]:
    """执行任务分配,返回 (分配结果, 未分配任务 ID)。签名与行为保持向后兼容。"""
    allocations, unassigned, _ = _run(uavs, tasks, algorithm, params, None, None, "auto")
    return allocations, unassigned


def allocate_with_plans(
    uavs: list[UAV],
    tasks: list[Task],
    algorithm: str = "hungarian",
    params: dict | None = None,
    stations: list | None = None,
    sigma: float | None = None,
    energy_strategy: str = "auto",
) -> tuple[list[TaskAllocation], list[str], list[RechargePlan]]:
    """执行任务分配,返回 (分配结果, 未分配任务 ID, 补给计划)。供 API 端点使用。"""
    return _run(uavs, tasks, algorithm, params, stations, sigma, energy_strategy)


def list_available_algorithms() -> list[dict]:
    """列出可用的任务分配算法"""
    return list_algorithms(AlgorithmCategory.TASK_ALLOCATION)
