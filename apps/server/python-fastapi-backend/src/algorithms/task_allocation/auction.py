"""拍卖算法 — 分布式竞价任务分配"""

from src.models.models import UAV, Task, TaskAllocation
from src.utils.utils import distance

PRIORITY_WEIGHT = {"low": 1.0, "medium": 1.5, "high": 2.0, "urgent": 3.0}


def auction_allocate(
    uavs: list[UAV],
    tasks: list[Task],
    max_iterations: int = 100,
    **kwargs,
) -> tuple[list[TaskAllocation], list[str]]:
    """拍卖算法实现"""
    if not uavs or not tasks:
        return [], [t.id for t in tasks]

    prices: dict[str, float] = {t.id: 0.0 for t in tasks}
    assignment: dict[str, str] = {}
    unassigned_tasks = [t.id for t in tasks]
    task_map = {t.id: t for t in tasks}
    uav_map = {u.id: u for u in uavs}

    for _ in range(max_iterations):
        if not unassigned_tasks:
            break

        new_unassigned = []
        for task_id in unassigned_tasks:
            task = task_map[task_id]
            best_bid = -1.0
            best_uav_id: str | None = None

            for uav in uavs:
                if uav.id in assignment.values():
                    continue

                d = distance(uav.position, task.position)
                w = PRIORITY_WEIGHT.get(task.priority, 1.0)
                valuation = d * w
                bid = valuation - prices[task_id]

                if bid > best_bid:
                    best_bid = bid
                    best_uav_id = uav.id

            if best_uav_id is not None:
                assignment[task_id] = best_uav_id
                prices[task_id] += best_bid * 0.1
            else:
                new_unassigned.append(task_id)

        unassigned_tasks = new_unassigned

    allocations = [
        TaskAllocation(
            uav_id=uav_id,
            task_id=task_id,
            estimated_cost=distance(uav_map[uav_id].position, task_map[task_id].position),
        )
        for task_id, uav_id in assignment.items()
    ]

    return allocations, unassigned_tasks
