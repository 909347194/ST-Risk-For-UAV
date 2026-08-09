"""任务分配算法注册"""

from src.task_allocation.algorithms.hungarian import hungarian_allocate
from src.task_allocation.algorithms.auction import auction_allocate

REGISTRY: dict[str, callable] = {
    "hungarian": hungarian_allocate,
    "auction": auction_allocate,
}

ALGORITHM_INFO: list[dict] = [
    {
        "name": "hungarian",
        "description": "匈牙利算法 — 最优一对一匹配，适合任务数≈无人机数的场景",
        "params_schema": None,
    },
    {
        "name": "auction",
        "description": "拍卖算法 — 分布式竞价，适合大规模动态场景",
        "params_schema": {
            "max_iterations": {"type": "integer", "default": 100, "description": "最大迭代轮数"},
        },
    },
]

__all__ = ["REGISTRY", "ALGORITHM_INFO"]
