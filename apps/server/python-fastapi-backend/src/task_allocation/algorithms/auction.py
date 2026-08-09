"""拍卖算法 — 分布式竞价任务分配"""

from src.shared.models import UAV, Task, TaskAllocation
from src.shared.utils import distance


def auction_allocate(
    uavs: list[UAV],
    tasks: list[Task],
    max_iterations: int = 100,
    **kwargs,
) -> tuple[list[TaskAllocation], list[str]]:
    """
    拍卖算法实现。

    每个 UAV 对未分配任务出价，最高出价者获得任务，
    通过价格调节避免冲突，迭代直到所有任务分配完毕或达到最大轮数。
    """
    if not uavs or not tasks:
        return [], [t.id for t in tasks]

    priority_weight = {"low": 1.0, "medium": 1.5, "high": 2.0, "urgent": 3.0}

    # 任务价格（初始为 0）
    prices: dict[str, float] = {t.id: 0.0 for t in tasks}
    # 分配结果: task_id -> uav_id
    assignment: dict[str, str] = {}
    # 未分配的任务
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
                # 如果 UAV 已被分配，跳过（简化：一个 UAV 只分配一个任务）
                if uav.id in assignment.values():
                    continue

                d = distance(uav.position, task.position)
                w = priority_weight.get(task.priority, 1.0)
                valuation = d * w  # UAV 对任务的估值（越低越好）
                bid = valuation - prices[task_id]  # 出价

                if bid > best_bid:
                    best_bid = bid
                    best_uav_id = uav.id

            if best_uav_id is not None:
                assignment[task_id] = best_uav_id
                # 提高价格（下次竞争更难赢得）
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
