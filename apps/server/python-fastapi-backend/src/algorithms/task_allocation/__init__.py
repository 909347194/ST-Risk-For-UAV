"""任务分配算法"""

from src.algorithms.registry import register, AlgorithmCategory
from src.algorithms.task_allocation.hungarian import hungarian_allocate
from src.algorithms.task_allocation.auction import auction_allocate


def _register() -> None:
    register(
        AlgorithmCategory.TASK_ALLOCATION,
        "hungarian",
        hungarian_allocate,
        {
            "name": "hungarian",
            "description": "匈牙利算法 — 最优一对一匹配，适合任务数≈无人机数的场景",
            "params_schema": None,
        },
    )
    register(
        AlgorithmCategory.TASK_ALLOCATION,
        "auction",
        auction_allocate,
        {
            "name": "auction",
            "description": "拍卖算法 — 分布式竞价，适合大规模动态场景",
            "params_schema": {
                "max_iterations": {"type": "integer", "default": 100, "description": "最大迭代轮数"},
            },
        },
    )
